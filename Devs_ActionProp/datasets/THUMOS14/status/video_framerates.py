# the best way would be check the .mat files, but this will very well approximate

import os, sys
project_root = os.path.join(os.path.expanduser('~'), 'Dev/NetModules')
sys.path.append(project_root)

import numpy as np
import matplotlib.pyplot as plt
import glob
from PyUtils import load_utils
import progressbar
import scipy.io as sio

ambiguous_class = 'Ambiguous'
user_root = os.path.expanduser('~')
datast_name = 'THUMOS14'
dataset_path = os.path.join(user_root, 'datasets',datast_name)


def getIdNames(path_root=None, isAug=False):
    if path_root is None:
        path_root = os.path.join(dataset_path, 'info')

    th14classids = []
    th14classnames = []
    target_file = open(os.path.join(path_root, 'detclasslist.txt'), 'rb')
    for line in target_file:
        elements = line.split()
        th14classids.append(int(elements[0]))
        th14classnames.append(elements[1])

    if isAug:
        th14classids.append(0)
        th14classnames.append(ambiguous_class)
    return th14classids, th14classnames


def createKeys(classids, classnames):
    id2name = {}
    name2id = {}
    for s_classid, s_classname in zip(classids, classnames):
        id2name[str(s_classid)] = s_classname
        name2id[s_classname] = s_classid

    return id2name, name2id

def IoU(inteval1, inteval2):
    i1 = [min(inteval1), max(inteval1)]
    i2 = [min(inteval2), max(inteval2)]

    b_union = [min(i1[0], i2[0]), max(i1[1], i2[1])]
    b_inter = [max(i1[0], i2[0]), min(i1[1], i2[1])]

    union = b_union[1] - b_union[0]
    intersection = b_inter[1] - b_inter[0]
    return intersection*1./union


def getFilenames(split='val'):
    classids, classnames = getIdNames(isAug=True)
    annotation_directory = os.path.join(dataset_path, 'annotations')
    video_file_names = []

    for s_classname, class_id in zip(classnames,classids):
        target_filename = '{:s}_{:s}.txt'.format(s_classname, split)
        s_filename = os.path.join(annotation_directory, target_filename)
        s_file = open(s_filename, 'rb')
        for line in s_file:
            elements = line.strip().split()
            video_name = elements[0]
            action_idx = class_id
            start_s = float(elements[1])
            end_s = float(elements[2])
            if video_name in video_file_names:
                continue
            video_file_names.append(video_name)
    return video_file_names


def load_video_info(split='val'):
    video_info = {}
    video_info_path = '/home/zwei/datasets/THUMOS14/info/{:s}_info.txt'.format(split)
    with open(video_info_path, 'rb') as video_info_data:
        for line in video_info_data:
            elements = line.strip().split()
            video_name = elements[0]
            video_height = int(float(elements[1]))
            video_width = int(float(elements[2]))
            video_duration = float(elements[3])
            video_framerate = float(elements[4])
            s_video_info = {}
            s_video_info['width'] = video_width
            s_video_info['height'] = video_height
            s_video_info['duration'] = video_duration
            s_video_info['framerate'] = video_framerate

            video_info[video_name] = s_video_info
    return video_info



if __name__ == '__main__':



    video_info_val = load_video_info('val')
    video_info_tst = load_video_info('test')

    full_video_info = video_info_val
    full_video_info.update(video_info_tst)

    video_file_names_test = getFilenames(split='test')
    video_file_names_val = getFilenames(split='val')
    video_file_names = video_file_names_test + video_file_names_val


    save_file = '/home/zwei/datasets/THUMOS14/info/video_info.txt'

    video_info = {}
    pbar = progressbar.ProgressBar(max_value=len(video_file_names))
    for video_idx, s_video_name in enumerate(video_file_names):
        pbar.update(video_idx)
        s_info = full_video_info[s_video_name]
        video_info[s_video_name] = s_info

    load_utils.save_json(video_info, save_file)















