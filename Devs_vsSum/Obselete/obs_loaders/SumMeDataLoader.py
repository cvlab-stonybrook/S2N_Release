import sys
import vsSummDevs.datasets.SumMe.path_vars as dataset_pathvars
from vsSummDevs.datasets.SumMe import SumMeMultiViewFeatureLoader
import sklearn
import torch.utils.data as data
import numpy as np
import torch
videofile_stems = dataset_pathvars.file_names
videofile_stems.sort()

train_video_stems = videofile_stems[:20]
val_video_stems = videofile_stems[20:]


def convertlabels2segs(labels):
    # print"NotImplemented"
    n_users = labels.shape[1]
    label_indicators = []
    for user_idx in range(n_users):
        s_labels = labels[:, user_idx]
        startIdx = 0
        endIdx = len(s_labels)
        for idx in range(1, len(s_labels)):
            if s_labels[idx] == 1 and s_labels[idx - 1] == 0:
                startIdx = idx
            if s_labels[idx] == 0 and s_labels[idx - 1] == 1:
                endIdx = idx
                label_indicators.append([startIdx, endIdx])

    return label_indicators

def convertlabels2NonoverlappedSegs(labels):
    segments = convertlabels2segs(labels)
    boundaris = []
    for s_segment in segments:
        boundaris.extend(s_segment)
    boundaris = list(set(boundaris))
    boundaris = np.asarray(boundaris)
    idxes = np.argsort(boundaris)
    boundaris = boundaris[idxes]
    new_segments = []
    for i in range(1, len(boundaris)):
        new_seg = [boundaris[i-1], boundaris[i]]
        new_segments.append(new_seg)
    return new_segments


class Segment():
    def __init__(self, video_name):
        self.video_stem = video_name
    def initVector(self, indicatorVector):
        self.indicatorVector = indicatorVector
        indices = np.argwhere(indicatorVector==1)[0]
        self.startIdx = indices[0]
        self.endIdx = indices[-1]
        self.length = len(indicatorVector)
    def initId(self, startId, endId, length):
        self.indicatorVector = np.zeros(length)
        self.indicatorVector[startId:endId]=1
        self.startIdx = startId
        self.endIdx = endId
        self.length = length



def overlap(pred, true):
    n_elements = true.sum()
    n_overlap = (pred*true).sum()
    return n_overlap*1./n_elements

feature_set = {'ImageNet': [0, 1], 'Kinetics':[1, 2], 'Places':[2, 3], 'Moments': [3, 4], 'All':[0, 4]}


class Dataset(data.Dataset):

    def __init__(self, split='train', doSoftMax=False, L2Norm=False, clip_size=100, sample_rate=15, feature_type='ImageNet'):
        print "Softmax:\t{0}\tL2Norm\t{1}".format(doSoftMax, L2Norm)
        self.split = split
        if self.split == 'train':
            self.video_stems = train_video_stems


        elif self.split == 'val':
            self.video_stems = val_video_stems

        else:
            print "Unrecognized data split: {:s}".format(split)
            sys.exit(-1)
        self.clip_size = clip_size
        self.videofeatures = {}
        self.annotations = {}
        for s_video_stem in self.video_stems:
            s_video_features, s_labels, _ = SumMeMultiViewFeatureLoader.load_by_name(s_video_stem,doSoftmax=doSoftMax,
                                                                                     featureset=feature_set[feature_type])
            s_video_features = s_video_features[::sample_rate]
            s_labels = s_labels[::sample_rate]
            if self.split == 'val':
                s_labels = s_labels[:,:15] # if validation, keep top 15
            n_frames = s_video_features.shape[0]
            if s_video_features.shape[0] < clip_size:
                print "{:s} don't have enough frames, skipping".format(s_video_stem)
                continue
            if L2Norm:
                s_video_features = sklearn.preprocessing.normalize(s_video_features)
            self.videofeatures[s_video_stem] = s_video_features

            s_segs = convertlabels2segs(s_labels)
            s_annotations = []
            for s_seg in s_segs:
                s_annotation = Segment(s_video_stem)
                s_annotation.initId(startId=s_seg[0], endId=s_seg[1], length=n_frames)
                s_annotations.append(s_annotation)
            self.annotations[s_video_stem] = s_annotations
        self.r_overlap = 0.3

        self.n_videos = len(self.annotations)

        if self.split == 'train':
            self.dataset_size = 10000
        else:
            list_annotations = []
            for s_video_stem in self.annotations.keys():
                list_annotations.extend(self.annotations[s_video_stem])
            self.annotations = list_annotations
            self.dataset_size = len(self.annotations)


        self.counter = 0

    def __getitem__(self, index):

        if self.split == 'train':
            #TODO: check if this way is correct!
            video_idx = np.random.randint(0, self.n_videos)
            selected_video_name = self.video_stems[video_idx]
            selected_video_length = self.videofeatures[selected_video_name].shape[0]
            random_startIdx = np.random.randint(0, selected_video_length-self.clip_size)
            selected_range = np.zeros(selected_video_length)
            selected_range[random_startIdx:random_startIdx+self.clip_size]=1
            groundtruths = []
            for s_annotation in self.annotations[selected_video_name]:
                #TODO: this is all wrong here!
                if overlap(selected_range, s_annotation.indicatorVector)>= self.r_overlap:
                    groundtruths.append([s_annotation.startIdx-random_startIdx, min(s_annotation.endIdx - random_startIdx-1, self.clip_size-1)])


            # if len(groundtruths)>1:
            random_selector = np.random.randint(0, len(groundtruths))
            s_groundtruth = groundtruths[random_selector]
            s_feature = self.videofeatures[selected_video_name][random_startIdx:random_startIdx+self.clip_size]
        else:

            s_annotation = self.annotations[index]

            frame_start = max(s_annotation.startIdx - np.random.randint(0, 50), 0)
            frame_end = frame_start + self.clip_size
            if frame_end > s_annotation.length:
                offset = frame_end-s_annotation.length
                frame_start -=offset
                frame_end = s_annotation.length


            s_groundtruth = torch.LongTensor([s_annotation.startIdx-frame_start, min(s_annotation.endIdx-frame_start-1, self.clip_size-1)])
            s_feature = torch.from_numpy(self.videofeatures[s_annotation.video_stem][frame_start:frame_end])




        return s_feature, s_groundtruth

    def __len__(self):
        return self.dataset_size # Predefine size...

if __name__ == '__main__':

    sDataset = Dataset(split='val')
    # HicoLoader = torch.utils.data.DataLoader(HicoDataset, batch_size=20, shuffle=False)
    for i, (image, label) in enumerate(sDataset):

        print "DEBUG"

