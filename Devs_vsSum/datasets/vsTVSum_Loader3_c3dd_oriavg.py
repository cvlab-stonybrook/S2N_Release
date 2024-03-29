# load labels from original TVSum labels
# the ground truth is by taking average of all annoatators, and use DP to generate a new ground truth
# one ground truth for each video
# use c3d features
import os
import sys

project_root = os.path.join(os.path.expanduser('~'), 'Dev/NetModules')
sys.path.append(project_root)

import h5py
import pickle as pkl
import Devs_vsSum.datasets
import progressbar
import torch.utils.data as data
from Devs_vsSum.datasets import KyLoader
import LoaderUtils
import numpy as np
import torch
import scipy.io as sio
import random
import math

from Devs_vsSum.SumEvaluation import rep_conversions, NMS

user_root = os.path.expanduser('~')

KY_dataset_path = os.path.join(os.path.expanduser('~'), 'datasets/KY_AAAI18/datasets')
# datasetpaths = {'summe': SumMe_paths, 'tvsum': TVSum_paths}
# data_loaders = {'summe': SumMeLoader, 'tvsum': TVSumLoader}

np.random.seed(0)
random.seed(0)

# train_val_perms = {'summe': np.random.permutation(25), 'tvsum': np.random.permutation(50)}


def compute_intersection(action, window):
    y1 = np.maximum(action[0], window[0])
    y2 = np.minimum(action[1], window[1])

    intersection = np.maximum(y2 - y1 + 1, 0)
    intersection_rate = intersection * 1. / (action[1] - action[0] + 1)
    return intersection_rate
    # union = box_area + boxes_area[:] - intersection[:]
    # if intersection>0:
    #     return True
    # else:
    #     return False


class cDataset(data.Dataset):
    def __init__(self, dataset_name='TVSum', split='train', seq_length=90, overlap=0.9, sample_rate=None,
                 feature_file_ext='npy', rdOffset=False, rdDrop=False, train_val_perms=None, data_path=None):
        if dataset_name.lower() not in ['summe', 'tvsum']:
            print('Unrecognized dataset {:s}'.format(dataset_name))
            sys.exit(-1)
        self.dataset_name = dataset_name
        self.feature_file_ext = feature_file_ext
        self.split = split

        # self.feature_directory = os.path.join(user_root, 'datasets/%s/features/c3dd-red500' % (dataset_name))
        self.feature_directory = os.path.join(data_path, '%s/features/c3dd-red500' % (dataset_name))
        self.filenames = os.listdir(self.feature_directory)
        self.filenames = [f.split('.', 1)[0] for f in self.filenames]
        self.filenames.sort()
        n_files = len(self.filenames)
        # selected_perms = range(n_files)
        # if self.split == 'train':
        #     selected_perms = train_val_perms[:int(0.8 * n_files)]
        # elif self.split == 'val':
        #     selected_perms = train_val_perms[int(0.8 * n_files):]
        # else:
        #     print("Unrecognized split:{:s}".format(self.split))
        # self.filenames = [self.filenames[i] for i in selected_perms]
        self.filenames = [self.filenames[i] for i in train_val_perms]
        update_n_files = len(self.filenames)

        if sample_rate is None:
            self.sample_rate = [1, 2, 4]
        else:
            self.sample_rate = sample_rate
        self.seq_len = seq_length
        self.overlap = overlap
        self.rdOffset = rdOffset
        self.rdDrop = rdDrop

        print("Processing {:s}\t{:s} data".format(self.dataset_name, self.split))
        print("num_videos:{:d} clip len:{:d} sample_rate: ".format(len(self.filenames), self.seq_len) + ' '.join(
            str(self.sample_rate)))

        KY_dataset_path = os.path.join(data_path, 'KY_AAAI18/datasets')
        Kydataset = KyLoader.loadKyDataset(self.dataset_name.lower(), file_path=os.path.join(KY_dataset_path, 'eccv16_dataset_{:s}_google_pool5.h5'.format(dataset_name.lower())))
        conversion = KyLoader.loadConversion(self.dataset_name.lower(), file_path=os.path.join(KY_dataset_path, '{:s}_name_conversion.pkl'.format(dataset_name.lower())))
        self.raw2Ky = conversion[0]
        self.Ky2raw = conversion[1]

        self.full_features = {}
        self.instances = []
        self.maximum_outputs = 0
        print("Creating training instances")
        pbar = progressbar.ProgressBar(max_value=len(self.filenames))
        n_positive_instances = 0
        n_positive_train_samples = 0
        n_total_train_samples = 0
        n_users = 0
        n_notselected_seq = 0

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        raw_data_path = os.path.join(project_root, 'Devs_vsSum/datasets/TVSum/TVSumRaw.pkl')
        raw_annotation_data = pkl.load(open(raw_data_path, 'rb'))

        for file_dix, s_filename in enumerate(self.filenames):
            pbar.update(file_dix)
            Kykey = self.raw2Ky[s_filename]
            s_usersummaries = Kydataset[Kykey]['user_summary'][...]
            s_usersummaries = s_usersummaries.transpose()
            n_frames = s_usersummaries.shape[0]

            raw_user_summaris = np.array(raw_annotation_data[s_filename])
            raw_user_summaris = raw_user_summaris.transpose()
            # raw_user_summaris_01 = []
            # for s_raw_user_summary in raw_user_summaris:
            #     assert len(s_raw_user_summary) == n_frames

            #     s_raw_user_summary = np.expand_dims(np.array(s_raw_user_summary), -1)
            #     s_summary_segments, s_summary_scores = LoaderUtils.convertscores2segs(s_raw_user_summary)
            #     s_selected_segments = rep_conversions.selecteTopSegments(s_summary_segments, s_summary_scores, n_frames)
            #     # raw_user_summaris_01.append(s_segments)
            #     s_frame01scores = rep_conversions.keyshots2frame01scores(s_selected_segments, n_frames)
            #     raw_user_summaris_01.append(s_frame01scores)
            # raw_user_summaris_01 = np.stack(raw_user_summaris_01, axis=1)

            raw_combine_summaris = np.mean(raw_user_summaris, 1, keepdims=True)
            s_segments, s_segment_scores = LoaderUtils.convertscores2segs(raw_combine_summaris)
            s_selected_segments = rep_conversions.selecteTopSegments(s_segments, s_segment_scores, n_frames)
            s_frame01scores = rep_conversions.keyshots2frame01scores(s_selected_segments, n_frames)
            s_frame01scores = s_frame01scores.reshape([-1, 1])

            # load features
            # TODO: if use dimension reduced feature, this need to change to read numpy files
            s_features = np.load(
                os.path.join(self.feature_directory, '{:s}.{:s}'.format(s_filename, self.feature_file_ext)))
            # the size of s_features is: [length, fea_dim]
            # s_features = s_features['fc7']
            s_features_len = len(s_features)
            # the length of c3d feature is larger than annotation, choose middles to match
            assert abs(n_frames - s_features_len) < 6, 'annotation and feature length not equal! {:d}, {:d}'.format(
                n_frames, s_features_len)
            offset = abs(s_features_len - n_frames) / 2
            s_features = s_features[offset:offset + n_frames]
            self.full_features[s_filename] = s_features

            s_n_users = s_frame01scores.shape[1]
            n_users += s_n_users

            # s_segments = LoaderUtils.convertlabels2segs(s_usersummaries) # load segments, check this function...
            # TODO: starting from here, you may consider changing it according to dataloader_c3dd_aug_fast
            for s_user in range(s_n_users):
                s_segments = LoaderUtils.convertlabels2segs(
                    s_frame01scores[:, [s_user]])  # load segments, check this function...
                n_positive_instances += len(s_segments)
                for s_sample_rate in self.sample_rate:
                    s_seq_len = self.seq_len * s_sample_rate
                    # only pick sequence whose length are longer than length to be picked
                    if s_seq_len <= n_frames:
                        start_idx = 0
                        isInbound = True
                        while start_idx < n_frames and isInbound:
                            end_idx = start_idx + s_seq_len
                            # UPDATE: cannot set to >, since we want to set isInbound to False this time
                            if end_idx >= n_frames:
                                isInbound = False
                                start_idx = start_idx - (end_idx - n_frames)
                                end_idx = n_frames

                            s_instance = {}
                            s_instance['name'] = s_filename
                            s_instance['start'] = start_idx
                            s_instance['end'] = end_idx
                            s_instance['actions'] = []
                            s_instance['sample_rate'] = s_sample_rate
                            s_instance['n_frames'] = n_frames
                            # TODO: also think about here, perhaps keep the ones that are overlap with the current clip over a threshod?
                            # TODO: in this way, how are we assigning them scores?
                            s_instance_window = [start_idx, end_idx]

                            for s_action in s_segments:
                                # Update: here include the partially overlaps...
                                if compute_intersection(s_action, s_instance_window) == 1:
                                    s_action_start = max(s_action[0], s_instance_window[0])
                                    s_action_end = min(s_action[1],
                                                       s_instance_window[1] - 1)  # TODO:check if here should minus 1
                                    # TODO: add overlap rate here!
                                    s_instance['actions'].append([s_action_start, s_action_end])

                            if len(s_instance['actions']) > self.maximum_outputs:
                                self.maximum_outputs = len(s_instance['actions'])
                            self.instances.append(s_instance)
                            n_positive_train_samples += len(s_instance['actions'])
                            start_idx = int(start_idx + (1 - self.overlap) * s_seq_len)
                    else:
                        n_notselected_seq += 1

        n_total_train_samples = len(self.instances) * self.maximum_outputs
        self.n_total_train_samples = n_total_train_samples
        self.n_positive_train_samples = n_positive_train_samples
        print(
            "{:s}\t{:d} video clips, {:d} training instances, {:d} positive examples, max instance per segment:{:d}, total number users:{:d}, not selected sequences:{:d}, total:{:d}, total pos:{:d}".
            format(split, update_n_files, len(self.instances), n_positive_instances, self.maximum_outputs, n_users, n_notselected_seq, n_total_train_samples, n_positive_train_samples))

    def random_drop_feats(self, input_feature):
        flip_coin = random.randint(0, 1)
        if flip_coin:
            return input_feature
        else:
            feature_len = input_feature.shape[0]
            rperm = np.random.permutation(self.seq_len - 1)[
                    :int(feature_len * 0.075)] + 1  # remove the awkward situation of sampling at 0
            rpreplace = rperm - 1
            input_feature[rperm, :] = input_feature[rpreplace, :]
            return input_feature

    def __getitem__(self, index):
        # ONLY in this part the sample rate jumps in
        s_instance = self.instances[index]

        # s_full_feature = np.load(os.path.join(self.feature_directory, '{:s}.{:s}'.format(s_instance['name'], self.feature_file_ext)))
        s_full_feature = self.full_features[s_instance['name']].copy()

        clip_start_position = s_instance['start']
        clip_end_position = s_instance['end']
        n_frames = min(s_instance['n_frames'], s_full_feature.shape[0])
        # if self.rdDrop:
        #     s_full_feature = self.random_drop_feats(s_full_feature)

        s_sample_rate = s_instance['sample_rate']

        if self.rdOffset:
            offset = random.randint(-int(self.seq_len * s_sample_rate * (1 - self.overlap) * 0.5),
                                    int(self.seq_len * s_sample_rate * (1 - self.overlap) * 0.5))
            if clip_end_position + offset > 0 and clip_end_position + offset < n_frames and clip_start_position + offset >= 0 and clip_start_position + offset < n_frames:
                clip_start_position += offset
                clip_end_position += offset

        s_clip_feature = s_full_feature[int(clip_start_position):int(clip_end_position):s_sample_rate]
        if self.rdDrop:
            s_clip_feature = self.random_drop_feats(s_clip_feature)

        assert s_clip_feature.shape[0] == self.seq_len, 'feature size wrong!'
        s_start_idxes = np.zeros(self.maximum_outputs, dtype=int)
        s_end_idxes = np.zeros(self.maximum_outputs, dtype=int)
        n_effective_idxes = len(s_instance['actions'])
        actionness_scores = -np.ones(self.seq_len)

        for idx in range(n_effective_idxes):

            p_start_position = ((s_instance['actions'][idx][0] - clip_start_position))
            p_end_position = ((s_instance['actions'][idx][1] - clip_start_position))
            if p_start_position < 0 or p_end_position >= self.seq_len * s_sample_rate:
                n_effective_idxes -= 1
                continue

            s_start_idxes[idx] = int(math.floor(p_start_position * 1. / s_sample_rate))
            s_end_idxes[idx] = int(math.floor(p_end_position * 1. / s_sample_rate))
            if s_start_idxes[idx] == s_end_idxes[idx]:
                actionness_scores[s_start_idxes[idx]] = 1
            else:
                actionness_scores[s_start_idxes[idx]:s_end_idxes[idx]] = 1
            assert s_start_idxes[idx] >= 0 and s_start_idxes[idx] < self.seq_len, '{:d} start wrong!'.format(
                s_start_idxes[idx])
            assert s_end_idxes[idx] >= 0 and s_end_idxes[idx] >= s_start_idxes[idx] and s_end_idxes[idx] < self.seq_len, \
                '{:d} end wrong'.format(s_end_idxes[idx])

        s_clip_feature = torch.FloatTensor(s_clip_feature).transpose(0, 1)
        s_start_idxes = torch.FloatTensor(s_start_idxes)
        s_end_idxes = torch.FloatTensor(s_end_idxes)
        n_effective_idxes = torch.LongTensor([n_effective_idxes])
        actionness_scores = torch.FloatTensor(actionness_scores)
        return s_clip_feature, s_start_idxes, s_end_idxes, n_effective_idxes, actionness_scores

    def __len__(self):

        return len(self.instances)


if __name__ == '__main__':

    from torch.utils.data import DataLoader

    sDataset = cDataset(dataset_name='SumMe', split='val', seq_length=90, overlap=0.9, sample_rate=[4], rdOffset=True,
                        rdDrop=True)
    train_dataloader = DataLoader(sDataset,
                                  batch_size=32,
                                  shuffle=False,
                                  num_workers=4)

    pbar = progressbar.ProgressBar(max_value=len(train_dataloader))
    offline_dataset = {}
    effective_example_length = []
    for idx, data in enumerate(train_dataloader):
        pbar.update(idx)
        start_idxes = data[1]
        end_idxes = data[2]
        effective_indices = data[3]