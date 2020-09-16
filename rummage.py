#!/usr/bin/python
from __future__ import print_function

# This is really Pillow... This does not go as good of a job as exiftool.
from PIL import Image, ExifTags
import sys
import os
import warnings
import datetime
import hashlib
import pickle
import subprocess
import json
from os import path, stat
import re
sys.path.insert(0, "/home/schwager/Projects/Pixalamode/debug_print")

# Found via Settings -> Project Interpreter -> Show All -> Show paths button
# (otherwise it's flagged as an error)
from debug_print import Debug
debug = Debug(True)

MANIFEST="rummage_pickle_manifest"

# Exif files don't contain these strings in their names
NOT_STARTSWITH = ["."]
NOT_CONTAINS = [".txt"]
NOT_ENDSWITH = [".db", ".info", ".docx", ".exe", ".pdf", ".url"]

# These are the names in the top-level of the overall dict
EXIF_UNRECOGNIZED_DICT = "exif_unrecognized"
EXIF_NO_DATES_DICT = "exif_no_dates"
EXIF_IGNORE_BASED_ON_NAME_DICT = "exif_ignore_based_on_name"
EXIF_NO_ATTRIBUTES_DICT = "exif_no_attributes"
EXIF_UNRECOGNIZED_ENTRY_DICT = "exif_unrecognized_entry"
EXIF_BIG_DIFF_ORIG_DIGITIZED_DICT = "exif_big_diff_orig_digitized"
EXIF_DATE_OK_DICT = "exif_date"
# "exif_date" is when everything is OK- we have good exif data.

# These will be the prefixes to the strings in the file_info_list, if they're not dates
NON_EXIF_IGNORED = "Ignored"
NON_EXIF_UNRECOGNIZED = "Unrecognized"
NON_EXIF_NO_ATTRIBUTES = "No_attributes"
NON_EXIF_UNRECOGNIZED_VALUE = "Unrecognized value"
NON_EXIF_BIG_DIFF = "Diff"
NO_ATTRIBUTES = "No attributes"

# return codes from functions
EXIF_IGNORE_BASED_ON_NAME = 0
EXIF_OK = 1
EXIF_NO_ATTRIBUTES = 2
EXIF_UNRECOGNIZED = 3
EXIF_BIG_DIFF_ORIG_DIGITIZED = 4
EXIF_UNRECOGNIZED_ENTRY = 5
EXIF_NO_DATES = 6
RETURN_CODE_MISSING = 99

output_code_dict = {
    EXIF_IGNORE_BASED_ON_NAME_DICT: EXIF_IGNORE_BASED_ON_NAME,
    EXIF_DATE_OK_DICT: EXIF_OK,
    EXIF_NO_ATTRIBUTES_DICT: EXIF_NO_ATTRIBUTES,
    EXIF_UNRECOGNIZED_DICT: EXIF_UNRECOGNIZED,
    EXIF_BIG_DIFF_ORIG_DIGITIZED_DICT: EXIF_BIG_DIFF_ORIG_DIGITIZED,
    EXIF_UNRECOGNIZED_ENTRY_DICT: EXIF_UNRECOGNIZED_ENTRY,
    EXIF_NO_DATES_DICT: EXIF_NO_DATES
}

warnings.simplefilter('error', Image.DecompressionBombWarning)

class Rummage:
    """
    Class that represents a rummage through the local filesystem, populating a
    pickle file and keeping a dictionary for you to reference.

    Results are stored in dictionaries. The top level dictionary is
    exif_dates_dict[]      it contains:
        "exif_unrecognized"
        "exif_no_dates"
        "exif_ignore_based_on_name"
        "exif_no_attributes"
        "exif_unrecognized_entry"
        "exif_big_diff_orig_digitized"
        "exif_date"
    These are the entries inside the dictionary. They are themselves dictionaries.

    Good results are stored in exif_dates_dict[exif_date[]]
    """
    def __init__(self, directory):
        if not os.path.exists(directory):
            raise (FileNotFoundError)

        if not os.path.isdir(directory):
            raise (NotADirectoryError)

        dir_hash = hashlib.sha1()
        dir_hash.update(directory.encode('utf-8'))
        dir_hash = dir_hash.hexdigest()
        self.opened_pickle = False

        self.pickle_dump = dir_hash + ".pickle"

        self._exif_dates_dict = {}

        for dirname, subdir_list, file_list in os.walk(directory):
            # print (">>> =========", dirname, "=========================")
            for file in file_list:
                filename = dirname + "/" + file
                filename = filename.rstrip()
                # TODO: Add an option to include links. This means that we ignore all symbolic links.
                if not os.path.islink(filename):
                    if os.path.isfile(filename):
                        return_code = self.do_exif(filename, self._exif_dates_dict)
                        if return_code == RETURN_CODE_MISSING:
                            raise RuntimeError("This should not happen: no return code from do_exif")

        if self.opened_pickle:
            to_delete = []
            for output_name in self._exif_dates_dict:
                file_dict = self._exif_dates_dict[output_name]
                for file_entry in file_dict:
                    file_entry_stat = file_dict[file_entry][0]
                    try:
                        file_stat = stat(file_entry)
                    except FileNotFoundError:
                        to_delete.append(file_entry)
                for file_entry in to_delete:
                    del file_dict[file_entry]
                    print("Deleted Entry:", file_entry)

        with open(self.pickle_dump, "wb") as f:
            pickle.dump(self._exif_dates_dict, f)

        manifest = None
        if os.path.exists(MANIFEST):
            manifest_file = open(MANIFEST)
            manifest = [x.split(" <BREAK> ")[1].rstrip() for x in manifest_file]
            manifest_file.close()

        if manifest is not None:
            for path in manifest:
                if not os.path.exists(path):
                    print ("WARNING:", path, "in manifest, but not on system.")
        if manifest is None or self.pickle_dump not in manifest:
            manifest_file = open(MANIFEST, "a")
            manifest_file.write(directory + " <BREAK> " + self.pickle_dump)
            manifest_file.write("\n")
            manifest_file.close()

    @property
    def exif_dates_dict(self):
        return self._exif_dates_dict

    @exif_dates_dict.setter
    def exif_dates_dict(self, exif_dates_dict):
        self._exif_dates_dict = exif_dates_dict
        if os.path.exists(self.pickle_dump):
            with open(self.pickle_dump, "rb") as f:
                self._exif_dates_dict = pickle.load(f)
            self.opened_pickle = True
        else:
            self._exif_dates_dict = {}


    def get_hash(self, a_filename):
        blocksize = 65536
        the_hash = hashlib.sha1()
        with open(a_filename, "rb") as fp:
            for block in iter(lambda: fp.read(blocksize), b""):
                the_hash.update(block)
        return the_hash.hexdigest()


    def str_hash(self, a_string):
        the_str_hash = hashlib.sha1()
        the_str_hash.update(a_string)
        return the_str_hash.hexdigest()


    # def write_output(output_name, file_object_dict, exif_dates_dict, filename, file_hash, output_string):
    #     """
    #     output_name is the dictionary key for the dictionary file_dict
    #     file_dict is a dictionary of all the filename's
    #     filename is the full path of the file
    #     output_string is any additional parts of the path
    #     """
    #     try:
    #         file_object_dict[output_name]
    #     except KeyError:
    #         file_object_dict[output_name] = open(output_name, 'w')
    #     file_object_dict[output_name].write(str(file_hash) + " " + str(exif_dates_dict[output_name][file_hash]) + '\n')


    def derive_date_from_path(self, filename):
        # Try to get date from the path...
        # 1. Filename: (2[01]|19)[0-9]2[0-2]

        # According to the docs (python3.4):
        # "The compiled versions of the most recent patterns passed to re.compile() and
        # the module-level matching functions are cached, so programs that use only a few regular
        # expressions at a time needn't worry about compiling regular expressions."
        regexp_to_check = [r'((19)|(20)|(21))[0-9][0-9][0-1][0-9][0-3][0-9]',
                           r'((19)|(20)|(21))[0-9][0-9]\W[0-1][0-9]\W[0-3][0-9]']
        basename = path.basename(filename)
        for regexp in regexp_to_check:
            pattern = re.compile(regexp)
            match = pattern.search(basename)
            if match:
                return match.group(1)
        return None

    def compare_stats(self, stat0, stat1):
        """
        Compare a couple of stats of two stat_result tuples.
        From the Python3 docs:
        For backward compatibility, a stat_result instance is also accessible as a
        tuple of at least 10 integers giving the most important (and portable) members
        of the stat structure, in the order
        st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size, st_atime, st_mtime, st_ctime
        :param stat0:
        :param stat1:
        :return: True if the same, False if not.
        """

        if stat0.st_mtime != stat1.st_mtime:
            return False
        if stat0.st_size != stat1.st_size:
            return False
        return True

    def check_existing_stats(self, exif_dates_dict, filename, stat_of_file):
        global output_code_dict
        for output_name in exif_dates_dict:
            file_dict = exif_dates_dict[output_name]
            try:
                file_entry = file_dict[filename]
                if self.compare_stats(file_entry[0], stat_of_file):
                    return output_code_dict[output_name]
            except KeyError:
                pass
        return RETURN_CODE_MISSING


    def get_exif_from_tool(self, file_path, file_info_list):
        try:
            # -CreateDate may work well here, too.
            args=["/usr/bin/exiftool", "-n", "-S", "-j",
                 file_path, "-MIMEType", "-MediaCreateDate",
                 "-DateTime", "-DateTimeOriginal", "-DateTimeDigitized"]
            # exiftool_output = subprocess.check_output(args=args)
            process = subprocess.Popen(args=args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            exiftool_output, exiftool_error = process.communicate()
            exiftool_output = exiftool_output.decode("utf-8")
            if exiftool_error:
                exiftool_error = exiftool_error.decode("utf-8")
                exiftool_error = exiftool_error.replace("\n", " ")
                print ("ERROR:", exiftool_error)
            exiftool_output = exiftool_output.replace("\n", " ")
            # this returns a list
            exiftool_output = json.loads(exiftool_output)
            exiftool_output = exiftool_output[0]
            # if you have MIMEType, you're a media file.
            if "MIMEType" not in exiftool_output:
                return 0
            if "MediaCreateDate" in exiftool_output:
                print("***EXIFTOOL: found MediaCreateDate", file_path)
            elif "DateTimeOriginal" in exiftool_output:
                print("***EXIFTOOL: found DateTimeOriginal", file_path)
            elif "DateTimeDigitized" in exiftool_output:
                print ("***EXIFTOOL: found DateTimeDigitized", file_path)
            elif "DateTime" in exiftool_output:
                print ("***EXIFTOOL: found DateTime", file_path)
            else:
                print ("***EXIFTOOL: checked, but no proper Date", file_path)
            return exiftool_output
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print ("ERROR: exiftool call on", file_path)
            return None


    # exif_found_files["exif_data"]=file_dict[hash]
    # file_dict[hash]=[filename, output_string]
    def populate_file_dict(self, output_name, exif_dates_dict, file_name, file_info_list):
        """
        Arguments:
        output_name- a name like "exif_date", "exif_unrecognized", etc.
        exif_dates_dict- dictionary containing dictionaries of output_name's. Keys are hashes, values are lists of
        pairs of (filename, output_string)
        filename - the file being stored
        file_hash - its hash
        output_string - an additional string to be added to the list, which is stored in output_type_dict
        """
        # print (file_info_list)
        stat = file_info_list[0]
        output_string = file_info_list[1]
        hash = file_info_list[2]
        try:
            file_dict=exif_dates_dict[output_name]
        except KeyError:
            file_dict={}
            exif_dates_dict[output_name]=file_dict
        # need_file_rehash = False
        # try:
        #     original_file_stat = file_dict[file_name][0]
        #     if not compare_stats(stat, original_file_stat):
        #         need_file_rehash = True
        #         del file_dict[file_name]
        #         print("File to be replaced because it was updated:", file_name)
        #         # TEST!!!!!!!!!!!!!!
        #     else:
        #         print ("File already there", file_name)
        # except KeyError:
        #     need_file_rehash = True
        # if need_file_rehash:
        file_hash = self.get_hash(file_name)
        file_dict[file_name] = [stat, output_string, file_hash]
        print("ADDED:", output_name, "FILE:", file_name, file_dict[file_name])
        # file_dict[(filename, stat)].append((file_hash, output_string))

        # print ("Type:", output_name, "entry:", file_hash, "list:", filename, output_string)
        # print ("============= DICT ==========")
        # print (exif_dates_dict)
        # print ("============= ==== ==========")
        # print ("Populated:", file_hash, exif_dates_dict[output_name][file_hash])
        # print ("...........")


    def perform_storage(self, output_name, exif_dates_dict, file_path, file_info_list):
        """

        :param output_name:
        :param file_object_dict:
        :param exif_dates_dict:
        :param file_info_list: A list including: file's absolute path, file's stat() object, and
                               date (or notice) string- eg "Ignored" or "2013-06-24 16:14:05"
        :param file_hash:
        :return:
        """
        self.populate_file_dict(output_name, exif_dates_dict, file_path, file_info_list)
        # write_output(output_name, file_object_dict, exif_dates_dict, filename, file_hash, output_string)


    def get_exif(self, img_file):
        try:
            img = Image.open(img_file)
        except IOError:
            return 0
        # exif_data = img._getexif()
        try:
            exif = {
                ExifTags.TAGS[k]: v
                for k, v in img._getexif().items()
                if k in ExifTags.TAGS
            }
        except AttributeError:
            #print ('x ', img_file, ": has no recognizable attributes")
            exif=None
        img.close()
        if exif is 0 or exif is None:
            pass
        return exif

    def compare_dates(self, exif, tag_date1, tag_date2):
        """
        Returns a string depending on what it finds in the comparison.
        """
        d1 = exif.get(tag_date1, None)
        if d1 is None:
            return "No comparison possible for (None): " + tag_date1 + " to " + tag_date2
        d2 = exif.get(tag_date2, None)
        if d2 is None:
            return "No comparison possible for (None): " + tag_date2 + " to " + tag_date1
        if d1 != d2:
            return "Differ: " + tag_date1 + " " + exif.get(tag_date1) + " ::: " + tag_date2 + " " + exif.get(tag_date2)
        else:
            return "Same: " + d1 + " " + tag_date1 + " " + tag_date2


    def do_exif(self, filename, exif_dates_dict):
        """
        returns:
        0 - File was ignored, entry saved to EXIF_IGNORE_BASED_ON_NAME_DICT
        1 - OK, valid Exif date was found.
        2 - No Exit attributes found, entry is saved to EXIF_NO_ATTRIBUTES_DICT
        3 - Exif was unrecognized, entry saved to EXIF_UNRECOGNIZED_DICT
        4 - Large difference between DateTimeOriginal and DateTimeDigitized, entry is saved
            to EXIF_BIG_DIFF_ORIG_DIGITIZED_DICT
        5 - Error in the Exif data, entry saved to EXIF_UNRECOGNIZED_ENTRY_DICT
        Based on the exif data, this file may be manifested more than once.
        """
        global NOT_STARTSWITH
        global NOT_CONTAINS
        global NOT_ENDSWITH

        global EXIF_UNRECOGNIZED_DICT
        global EXIF_NO_DATES_DICT
        global EXIF_IGNORE_BASED_ON_NAME_DICT
        global EXIF_NO_ATTRIBUTES_DICT
        global EXIF_UNRECOGNIZED_ENTRY_DICT
        global EXIF_BIG_DIFF_ORIG_DIGITIZED_DICT
        global EXIF_DATE_OK_DICT

        global NON_EXIF_IGNORED
        global NON_EXIF_UNRECOGNIZED
        global NON_EXIF_NO_ATTRIBUTES
        global NON_EXIF_UNRECOGNIZED_VALUE
        global NON_EXIF_BIG_DIFF
        global NO_ATTRIBUTES

        # Return codes
        global EXIF_IGNORE_BASED_ON_NAME
        global EXIF_OK
        global EXIF_NO_ATTRIBUTES
        global EXIF_UNRECOGNIZED
        global EXIF_BIG_DIFF_ORIG_DIGITIZED
        global EXIF_UNRECOGNIZED_ENTRY
        global RETURN_CODE_MISSING

        base=os.path.basename(filename)
        file_path = os.path.abspath(filename)

        # This will have 3 elements: the stat, the date/info string (appended below), and the hash
        file_info_list = [stat(filename), "", 0]

        # Don't redo files that already are in a dictionary
        code =  self.check_existing_stats(exif_dates_dict, file_path, file_info_list[0])
        if code != RETURN_CODE_MISSING:
            print ("File already there:", filename, "Full Path:", file_path)
            return code

        if base.startswith(".") or base.endswith((".db", ".info", ".docx", ".exe", ".pdf", ".url")):
            file_info_list[1] = NON_EXIF_IGNORED
            self.perform_storage(EXIF_IGNORE_BASED_ON_NAME_DICT, exif_dates_dict, file_path, file_info_list)
            return EXIF_IGNORE_BASED_ON_NAME

        for contain_str in NOT_CONTAINS:
            if contain_str in base:
                file_info_list[1] = NON_EXIF_IGNORED
                self.perform_storage(EXIF_IGNORE_BASED_ON_NAME_DICT, exif_dates_dict, file_path, file_info_list)
                return EXIF_IGNORE_BASED_ON_NAME

        exif = self.get_exif(file_path)
        if exif is 0 or exif is None:
            exif = self.get_exif_from_tool(file_path, file_info_list)
        if exif is 0:
            file_info_list[1] = NON_EXIF_UNRECOGNIZED
            self.perform_storage(EXIF_UNRECOGNIZED_DICT, exif_dates_dict, file_path, file_info_list)
            print ("Exif unrecognized for", file_path)
            return EXIF_UNRECOGNIZED
        if exif is None:
            file_info_list[1] = NO_ATTRIBUTES
            self.perform_storage(EXIF_NO_ATTRIBUTES_DICT, exif_dates_dict, file_path, file_info_list)
            return EXIF_NO_ATTRIBUTES
        # Get 3 values:
        # date_time, date_time_digitized, date_time_original

        # Return if no exif.
        # Print to an error
        # Get the three DateTime's in the dicts: <base>, Digitized, Original. Set to None if not found.
        # If ValueError, output to exif_datatime_unrecognized
        date_time = None
        date_time_digitized = None
        date_time_original = None
        media_create_date = None
        try:
            date_time = exif.get('DateTime', None)
            if date_time is not None:
                date_time = datetime.datetime.strptime(date_time, "%Y:%m:%d %H:%M:%S")
            date_time_digitized = exif.get('DateTimeDigitized', None)
            if date_time_digitized is not None:
                date_time_digitized = datetime.datetime.strptime(date_time_digitized, "%Y:%m:%d %H:%M:%S")
            date_time_original = exif.get('DateTimeOriginal', None)
            if date_time_original is not None:
                date_time_original = datetime.datetime.strptime(date_time_original, "%Y:%m:%d %H:%M:%S")
            media_create_date = exif.get('MediaCreateDate', None)
            if media_create_date is not None:
                media_create_date = datetime.datetime.strptime(media_create_date, "%Y:%m:%d %H:%M:%S")

            # we assume we'll return OK. Let's see...
            return_code = RETURN_CODE_MISSING
            # keyij=exif.keys()
            # keyij.sort()
            #
            # With the three dates:
            # If all the same: If valid values, write to exif_date.     ...If "None", write to exif_no_date
            # If it's not None, compare this date with the other dates.
            # If it's different than one that's not None, print a notice.
            # Start with date_time_original.
            # Then look at date_time_digitized.
            # Then look at date_time. This should cover most of the jpg and png files
            # Finally look at MediaCreateDate, which could be for .mp4 and other video media.
            #
            # They all agree -----------------------------------------
            if date_time == date_time_digitized == date_time_original == date_time == media_create_date == None:
                output_name=EXIF_NO_DATES_DICT
                return_code = EXIF_NO_DATES
                file_info_list[1] = str(date_time)
            elif date_time == date_time_digitized == date_time_original:
                output_name=EXIF_DATE_OK_DICT
                return_code = EXIF_OK
                file_info_list[1] = str(date_time)
            #########################################################
            # date_time_original priority ---------------------------
            elif date_time_original is not None:
                # report date_time_original vs digitized ------------
                if date_time_digitized is not None:
                    delta_date = date_time_original - date_time_digitized
                    if abs(delta_date.days) > 1 or abs(delta_date.seconds) > 43200:
                        # got_big_difference_original_digitized
                        file_info_list[1] = (NON_EXIF_BIG_DIFF + " DateTimeOriginal " +
                                              str(date_time_original) + " DateTimeDigitized " +
                                              str(date_time_digitized))
                        output_name = EXIF_BIG_DIFF_ORIG_DIGITIZED_DICT
                        return_code = EXIF_BIG_DIFF_ORIG_DIGITIZED
                    else:
                        file_info_list[1] = str(date_time_original)
                        output_name = EXIF_DATE_OK_DICT
                        return_code = EXIF_OK
                # report date_time_original vs date_time ------------
                elif date_time is not None:
                    # Timedelta's attributes are days, seconds, microseconds
                    delta_date = date_time_original - date_time
                    if delta_date.days > 1:
                        file_info_list[1] = str(date_time)
                        output_name = EXIF_DATE_OK_DICT
                        return_code = EXIF_OK
                    else:
                        file_info_list[1] = str(date_time_original)
                        output_name = EXIF_DATE_OK_DICT
                        return_code = EXIF_OK
                else:
                    file_info_list[1] = str(date_time_original)
                    output_name = EXIF_DATE_OK_DICT
                    return_code = EXIF_OK
            #########################################################
            # date_time_digitized priority --------------------------
            elif date_time_digitized is not None:
                # report digitized vs date_time
                if date_time is not None:
                    # got big difference date_time_digitized vs date_time
                    delta_date = date_time_digitized - date_time
                    #if abs(delta_date.days) > 1 or abs(delta_date.seconds) > 43200:
                    if delta_date.days > 1:
                        file_info_list[1] = str(date_time_digitized)
                    else:
                        file_info_list[1] = str(date_time)
                else:
                    file_info_list[1] = str(date_time_digitized)
                output_name = EXIF_DATE_OK_DICT
                return_code = EXIF_OK
            #########################################################
            elif date_time is not None:
                file_info_list[1] = str(date_time)
                output_name = EXIF_DATE_OK_DICT
                return_code = EXIF_OK
            elif media_create_date is not None:
                file_info_list[1] = str(media_create_date)
                print("MEDIA CREATE DATE:", file_info_list[1])
                output_name = EXIF_DATE_OK_DICT
                return_code = EXIF_OK
        except ValueError:
            # eg, date values of 0000:00:00 00-00-00 will throw this exception
            # We see that in MediaCreateDate, at least.

            # TODO: Add functionality to get the date value from the filename,
            # TODO: and add it to another dictionary, appropriately named.
            file_info_list[1] = (NON_EXIF_UNRECOGNIZED_VALUE + " DateTime: " + str(date_time) +
                                 " DateTimeDigitized: " + str(date_time_digitized) +
                                 " DateTimeOriginal: " + str(date_time_original) +
                                 " MediaCreateDate: " + str(media_create_date)
                                 )
            print ("VALUE ERROR:", file_info_list[1])
            output_name = EXIF_UNRECOGNIZED_ENTRY_DICT
            return_code = EXIF_UNRECOGNIZED_ENTRY
        self.perform_storage(output_name, exif_dates_dict, file_path, file_info_list)
        return return_code


        # TODO!!!!

        # print (compare_dates(exif, 'DateTime', 'DateTimeDigitized') + " " + filename)
        # print (compare_dates(exif, 'DateTime', 'DateTimeOriginal') + " " + filename)
        # print (compare_dates(exif, 'DateTimeDigitized',  'DateTimeOriginal') + " " + filename)


# ##########################################################################################
#
# ################ MAIN ####################################################################
#
# ##########################################################################################


#print (exif_data)


    #for the_hash in exif_dates_dict[output_name]:
    #    print (the_hash, exif_dates_dict[output_name][the_hash])
    #write_output(output_name, exif_found_file_objects, exif_dates_dict,
    #print (str(str_hash(output_name)))
    #print (exif_dates_dict[output_name])

if __name__=="__main__":
    directory = sys.argv[1]
    print(directory)

    rummage = Rummage(directory)
    for output_name in rummage.exif_dates_dict:
        print("----------------------------", output_name, "---------------------------")
        print("OUTPUT DICT:", output_name)

    pass
