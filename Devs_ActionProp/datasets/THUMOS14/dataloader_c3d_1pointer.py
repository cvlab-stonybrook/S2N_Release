
import torch.utils.data as data
from PIL import Image
import os
import os.path
import errno
import torch
import json
import codecs
from torchvision import datasets, transforms
#Update: trained based on generated ground truth from https://github.com/yjxiong/temporal-segment-networks

import random
random.seed(0)
import progressbar
import numpy as np
import scipy.io
np.random.seed(0)
import pickle as pkl
from PyUtils import load_utils
import pandas as pd
import math
import sys
import Losses.h_assign as match_functions
train_selected_perms = np.random.permutation(200)


def compute_intersection(action, window):

    y1 = np.maximum(action[0], window[0])
    y2 = np.minimum(action[1], window[1])

    intersection = np.maximum(y2-y1+1, 0)
    intersection_rate = intersection*1./(action[1]-action[0]+1)
    return intersection_rate



miss_name = ('video_test_0001292','video_validation_0000190')
user_root = os.path.expanduser('~')

class THUMOST14(data.Dataset):

    def __init__(self, seq_length=27, overlap=3, sample_rate=1, dataset_split='val', feature_file_ext='mat', stride=3, n_stack=4):
        self.feature_directory = os.path.join(user_root, 'datasets/THUMOS14/features/c3d')
        self.feature_file_ext = feature_file_ext
        self.data_split = dataset_split
        if dataset_split == 'train' or dataset_split=='val':
            self.annotation_file = os.path.join(user_root, 'Dev/NetModules/ActionLocalizationDevs/action_det_prep/thumos14_tag_val_proposal_list_c3d.csv')
        elif dataset_split == 'test':
            self.annotation_file = os.path.join(user_root, 'Dev/NetModules/ActionLocalizationDevs/action_det_prep/thumos14_tag_test_proposal_list_c3d.csv')
        else:
            print("Cannot recognize split: {:s}".format(dataset_split))
            sys.exit(-1)

        print("{:s}, Reading training data list from {:s}\t clip len:{:d}, sample rate: {:d}".format(self.data_split, self.annotation_file, seq_length, sample_rate))
        self.anchor_positions = []

        for s_stack in range(n_stack):
            s_positions = range(0, seq_length, stride**s_stack)
            for s_starting in s_positions:
                s_ending = s_starting + stride**s_stack
                self.anchor_positions.append([s_starting, s_ending])


        self.anchor_positions = np.asarray(self.anchor_positions)

        self.movie_instances = {}

        ground_truth = pd.read_csv(self.annotation_file, sep=' ')
        n_ground_truths = len(ground_truth)

        target_video_frms = ground_truth[['video-name', 'video-frames']].drop_duplicates().values
        self.frm_nums = {}
        self.video_list = []
        for s_target_videofrms in target_video_frms:
            self.frm_nums[s_target_videofrms[0]] = s_target_videofrms[1]
            self.video_list.append(s_target_videofrms[0])

        n_files = len(self.video_list)

        selected_perms = range(n_files)
        if dataset_split == 'train':
            selected_perms = train_selected_perms[:170]
        if dataset_split == 'val':
            selected_perms = train_selected_perms[170:]

        self.selected_video_list = [self.video_list[i] for i in selected_perms]

        for i_pos in range(n_ground_truths):
            s_ground_truth = ground_truth.loc[[i_pos]]
            movie_name = s_ground_truth['video-name'].values[0]
            if movie_name not in self.selected_video_list:
                continue
            n_frames = self.frm_nums[movie_name]
            if movie_name in miss_name:
                # print("Missing {:s}".format(movie_name))
                continue
            else:
                gt_start = s_ground_truth['f-init'].values[0]
                gt_end = min(s_ground_truth['f-end'].values[0], n_frames)
                if movie_name in self.movie_instances.keys():
                    self.movie_instances[movie_name].append((gt_start, gt_end))
                else:
                    self.movie_instances[movie_name] = [(gt_start, gt_end)]

        n_positive_instances = 0
        total_reps = 0
        #Update: during training, we can remove the repeats, in the test, the repeats come out as you have to evaluate on different overlapped clipps
        for s_name in self.movie_instances.keys():

            s_action_list = self.movie_instances[s_name]
            orig_len = len(s_action_list)
            s_action_list = list(set(s_action_list))
            s_action_list.sort() # sort from left to right
            cur_len = len(s_action_list)
            # print("{:s}\t reps{:d}".format(s_name, orig_len-cur_len))
            total_reps += orig_len - cur_len
            n_positive_instances += len(s_action_list)
            self.movie_instances[s_name] = s_action_list
        print("{:d} reps found".format(total_reps))

        self.instances = []
        self.maximum_outputs = 0
        self.seq_len = seq_length
        self.sample_rate = sample_rate
        s_debug_n_invalid = 0

        for s_movie_name in self.movie_instances.keys():

            s_movie_instance = self.movie_instances[s_movie_name]
            n_frames = self.frm_nums[s_movie_name]

            start_idx = 0
            isInbound = True
            while start_idx < n_frames and isInbound:
                end_idx = (start_idx + self.seq_len)
                #UPDATE: cannot set to >, since we want to set isInbound to False this time
                if end_idx >= n_frames:
                    isInbound = False
                    start_idx = start_idx - (end_idx-n_frames)
                    end_idx = n_frames

                s_instance = {}
                s_instance['name'] = s_movie_name
                s_instance['start'] = start_idx
                s_instance['end'] = end_idx
                s_instance['actions'] = []
                #TODO: also think about here, perhaps keep the ones that are overlap with the current clip over a threshod?
                #TODO: in this way, how are we assigning them scores?
                s_instance_window = [start_idx, end_idx]

                for s_action in s_movie_instance:
                    #Update: here include the partially overlaps...
                    if compute_intersection(s_action, s_instance_window) == 1:
                        s_action_start = max(s_action[0], s_instance_window[0])
                        s_action_end = min(s_action[1], s_instance_window[1]-1) #TODO:check if here should minus 1
                        # assert s_action_start<=s_action_end, 'check action start and action end differences'
                        if s_action_start > s_action_end:
                            s_debug_n_invalid += 1
                            continue
                        s_instance['actions'].append([s_action_start, s_action_end])
                if len(s_instance['actions']) > self.maximum_outputs:
                    self.maximum_outputs = len(s_instance['actions'])
                self.instances.append(s_instance)
                start_idx = int(start_idx + overlap)
        #TODO: solve this issue!
        print("{:d} invalid examples found!".format(s_debug_n_invalid))

        print("{:s}\t{:d} video clips, {:d} training instances, {:d} positive examples, max instance per segment:{:d}".
              format(dataset_split, len(self.movie_instances), len(self.instances), n_positive_instances, self.maximum_outputs))

    def __getitem__(self, index):
        # ONLY in this part the sample rate jumps in
        s_instance = self.instances[index]

        s_full_feature = scipy.io.loadmat(os.path.join(self.feature_directory, '{:s}.{:s}'.format(s_instance['name'], self.feature_file_ext)))['relu6']
        clip_start_position = s_instance['start']
        clip_end_position = s_instance['end']
        s_clip_feature = s_full_feature[int(clip_start_position):int(clip_end_position):self.sample_rate]
        assert s_clip_feature.shape[0] == self.seq_len/self.sample_rate, 'feature size wrong!'
        n_effective_idxes = len(s_instance['actions'])

        pointer_positions = np.zeros(self.maximum_outputs, dtype=int)
        # effective_indicators = np.zeros(self.maximum_outputs, dtype=int)
        # effective_indicators[:n_effective_idxes]=1
        if n_effective_idxes>0:
            p_positions = np.zeros([n_effective_idxes, 2])

            for idx in range(n_effective_idxes):
                p_start_position = ((s_instance['actions'][idx][0] - clip_start_position))
                p_end_position = ((s_instance['actions'][idx][1] - clip_start_position))
                p_positions[idx, :] = [p_start_position, p_end_position]

            ious = match_functions.compute_overlaps(p_positions, self.anchor_positions)
            match_cost = match_functions.toCostMatrix(ious)
            row_inds, col_inds = match_functions.linear_sum_assignment(match_cost)
            pointer_positions[:n_effective_idxes] = col_inds

        s_clip_feature = torch.FloatTensor(s_clip_feature).transpose(0, 1)
        n_effective_idxes = torch.LongTensor([n_effective_idxes])
        pointer_positions = torch.FloatTensor(pointer_positions)
        return s_clip_feature, pointer_positions, n_effective_idxes


    def __len__(self):

        return len(self.instances)


if __name__ == '__main__':
    from torch.utils.data import DataLoader


    thumos_dataset = THUMOST14(seq_length=27, overlap=3, sample_rate=1, dataset_split='train')
    train_dataloader = DataLoader(thumos_dataset,
                                  batch_size=10,
                                  shuffle=True,
                                  num_workers=4)

    pbar = progressbar.ProgressBar(max_value=len(train_dataloader))
    offline_dataset = {}
    for idx, data in enumerate(train_dataloader):
        pbar.update(idx)
        # clip_feature = data[0]
        # start_idxes = data[1]
        # end_idxes = data[2]
        # effective_idxes = [3]

