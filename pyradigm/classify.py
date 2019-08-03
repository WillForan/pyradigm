
__all__ = ['ClassificationDataset', ]

from pyradigm.base import BaseDataset, check_compatibility_BaseDataset
import numpy as np
import os
import pickle
import random
import sys
import traceback
import warnings
from collections import Counter, OrderedDict, Sequence
from itertools import islice
from os.path import isfile, realpath


class ClassificationDataset(BaseDataset):
    """
    The main class for user-facing ClassificationDataset.

    Note: samplet is defined  to refer to a single row in feature matrix X: N x p
    """

    def __init__(self,
                 dataset_path=None,
                 in_dataset=None,
                 data=None,
                 targets=None,
                 description='',
                 feature_names=None,
                 allow_nan_inf=False,
                 ):
        """
        Default constructor.
        Recommended way to construct the dataset is via add_samplet method,
        one samplet at a time, as it allows for unambiguous identification of
        each row in data matrix.

        This constructor can be used in 3 ways:
            - As a copy constructor to make a copy of the given in_dataset
            - Or by specifying the tuple of data, targets and classes.
                In this usage, you can provide additional inputs such as description
                and feature_names.
            - Or by specifying a file path which contains previously saved Dataset.

        Parameters
        ----------
        dataset_path : str
            path to saved Dataset on disk, to directly load it.

        in_dataset : Dataset
            Dataset to be copied to create a new one.

        data : dict
            dict of features (samplet_ids are treated to be samplet ids)

        targets : dict
            dict of targets
            (samplet_ids must match with data/classes, are treated to be samplet ids)

        description : str
            Arbitrary string to describe the current dataset.

        feature_names : list, ndarray
            List of names for each feature in the dataset.

        Raises
        ------
        ValueError
            If in_dataset is not of type Dataset or is empty, or
            An invalid combination of input args is given.
        IOError
            If dataset_path provided does not exist.

        """

        super().__init__(target_type=str,
                         allow_nan_inf=allow_nan_inf,
                         )

        if dataset_path is not None:
            if isfile(realpath(dataset_path)):
                # print('Loading the dataset from: {}'.format(dataset_path))
                self._load(dataset_path)
            else:
                raise IOError('Specified file could not be read.')
        elif in_dataset is not None:
            if not isinstance(in_dataset, self.__class__):
                raise TypeError('Invalid Class input: {} expected!'
                                 ''.format(self.__class__))
            if in_dataset.num_samplets <= 0:
                raise ValueError('Dataset to copy is empty.')
            self._copy(in_dataset)
        elif data is None and targets is None:
            self._data = OrderedDict()
            self._targets = OrderedDict()
            self._num_features = 0
            self._dtype = None
            self._description = ''
            self._feature_names = None
        elif data is not None and targets is not None:
            # ensuring the inputs really correspond to each other
            # but only in data and targets, not feature names
            self._validate(data, targets)

            # OrderedDict to ensure the order is maintained when
            # data/targets are returned in a matrix/array form
            self._data = OrderedDict(data)
            self._targets = OrderedDict(targets)
            self._description = description

            sample_ids = list(data)
            features0 = data[sample_ids[0]]
            self._num_features = features0.size \
                    if isinstance(features0,np.ndarray) \
                    else len(features0)
            self._dtype = type(data[sample_ids[0]])

            # assigning default names for each feature
            if feature_names is None:
                self._feature_names = self._str_names(self.num_features)
            else:
                self._feature_names = feature_names

        else:
            raise ValueError('Incorrect way to construct the dataset.')


    def _check_features(self, features):
        """
        Method to ensure features to be added are not empty and vectorized.

        Parameters
        ----------
        features : iterable
            Any data that can be converted to a numpy array.

        Returns
        -------
        features : numpy array
            Flattened non-empty numpy array.

        Raises
        ------
        ValueError
            If input data is empty.
        """

        if not isinstance(features, np.ndarray):
            features = np.asarray(features)

        if features.size <= 0:
            raise ValueError('provided features are empty.')

        if features.ndim > 1:
            features = np.ravel(features)

        return features

    @property
    def target_set(self):
        """Set of unique classes in the dataset."""

        return list(set(self._targets.values()))


    @property
    def target_sizes(self):
        """Returns the sizes of different objects in a Counter object."""
        return Counter(self._targets.values())


    @property
    def num_targets(self):
        """Total number of classes in the dataset."""
        return len(self.target_set)


    def sample_ids_in_class(self, class_id):
        """
        Returns a list of sample ids belonging to a given class.

        Parameters
        ----------
        class_id : str
            class id to query.

        Returns
        -------
        subset_ids : list
            List of sample ids belonging to a given class.

        """

        # subset_ids = [sid for sid in self.samplet_ids if self.classes[sid] == class_id]
        subset_ids = self.keys_with_value(self.classes, class_id)
        return subset_ids


    def get_class(self, target_id):
        """
        Returns a smaller dataset belonging to the requested classes.

        Parameters
        ----------
        target_id : str or list
            identifier(s) of the class(es) to be returned.

        Returns
        -------
        ClassificationDataset
            With subset of samples belonging to the given class(es).

        Raises
        ------
        ValueError
            If one or more of the requested classes do not exist in this dataset.
            If the specified id is empty or None

        """
        if target_id in [None, '']:
            raise ValueError("target id can not be empty or None.")

        if isinstance(target_id, str):
            target_ids = [target_id, ]
        else:
            target_ids = target_id

        non_existent = set(self.target_set).intersection(set(target_ids))
        if len(non_existent) < 1:
            raise ValueError(
                'These classes {} do not exist in this dataset.'.format(non_existent))

        subsets = list()
        for target_id in target_ids:
            subsets_this_class = self.keys_with_value(self._targets, target_id)
            subsets.extend(subsets_this_class)

        return self.get_subset(subsets)


    def random_subset(self, perc_in_class=0.5):
        """
        Returns a random sub-dataset (of specified size by percentage) within each
        class.

        Parameters
        ----------
        perc_in_class : float
            Fraction of samples to be taken from each class.

        Returns
        -------
        subdataset : ClassificationDataset
            random sub-dataset of specified size.

        """

        subsets = self.random_subset_ids(perc_in_class)
        if len(subsets) > 0:
            return self.get_subset(subsets)
        else:
            warnings.warn('Zero samples were selected. Returning an empty dataset!')
            return self.__class__()


    def random_subset_ids(self, perc_per_class=0.5):
        """
        Returns a random subset of sample ids (size in percentage) within each class.

        Parameters
        ----------
        perc_per_class : float
            Fraction of samples per class

        Returns
        -------
        subset : list
            Combined list of sample ids from all classes.

        Raises
        ------
        ValueError
            If no subjects from one or more classes were selected.
        UserWarning
            If an empty or full dataset is requested.

        """

        subsets = list()

        if perc_per_class <= 0.0:
            warnings.warn('Zero percentage requested - returning an empty dataset!')
            return list()
        elif perc_per_class >= 1.0:
            warnings.warn('Full or a larger dataset requested - returning a copy!')
            return self.samplet_ids

        # seeding the random number generator
        # random.seed(random_seed)

        for target_id, target_size in self.target_sizes.items():
            # samples belonging to the class
            this_class = self.keys_with_value(self.targets, target_id)
            # shuffling the sample order; shuffling works in-place!
            random.shuffle(this_class)
            # calculating the requested number of samples
            subset_size_this_class = np.int64(np.floor(target_size * perc_per_class))
            # clipping the range to [1, n]
            subset_size_this_class = max(1, min(target_size, subset_size_this_class))
            if subset_size_this_class < 1 or len(this_class) < 1 or this_class is None:
                # warning if none were selected
                raise ValueError(
                    'No samplets from class {} were selected.'.format(target_id))
            else:
                subsets_this_class = this_class[0:subset_size_this_class]
                subsets.extend(subsets_this_class)

        if len(subsets) > 0:
            return subsets
        else:
            warnings.warn('Zero samples were selected. Returning an empty list!')
            return list()


    def random_subset_ids_by_count(self, count_per_class=1):
        """
        Returns a random subset of sample ids of specified size by count,
            within each class.

        Parameters
        ----------
        count_per_class : int
            Exact number of samples per each class.

        Returns
        -------
        subset : list
            Combined list of sample ids from all classes.

        """

        subsets = list()

        if count_per_class < 1:
            warnings.warn('Atleast one sample must be selected from each class')
            return list()
        elif count_per_class >= self.num_samplets:
            warnings.warn('All samples requested - returning a copy!')
            return self.samplet_ids

        # seeding the random number generator
        # random.seed(random_seed)

        for target_id, target_size in self.target_sizes.items():
            # samples belonging to the class
            this_class = self.keys_with_value(self.targets, target_id)
            # shuffling the sample order; shuffling works in-place!
            random.shuffle(this_class)

            # clipping the range to [0, class_size]
            subset_size_this_class = max(0, min(target_size, count_per_class))
            if subset_size_this_class < 1 or this_class is None:
                # warning if none were selected
                warnings.warn('No samplets from class {} were selected.'
                              ''.format(target_id))
            else:
                subsets_this_class = this_class[0:count_per_class]
                subsets.extend(subsets_this_class)

        if len(subsets) > 0:
            return subsets
        else:
            warnings.warn('Zero samples were selected. Returning an empty list!')
            return list()


    def rename_targets(self, new_targets):
        """
        Helper to rename the classes, if provided by a dict keyed in by the
        orignal samplet_ids

        Parameters
        ----------
        new_targets : dict
            Dict of targets keyed in by sample IDs.

        Raises
        ------
        TypeError
            If targets is not a dict.
        ValueError
            If all samples in dataset are not present in input dict,
            or one of they samples in input is not recognized.

        """
        if not isinstance(new_targets, dict):
            raise TypeError('Input targets is not a dict!')
        if not len(new_targets) == self.num_samplets:
            raise ValueError('Too few items in dict - need {} samplet_ids'
                             ''.format(self.num_samplets))
        if not all([key in self.samplet_ids for key in new_targets]):
            raise ValueError('One or more unrecognized samplet_ids!')
        self._targets = new_targets


    def compatible(self, another):
        """
        Checks whether the input dataset is compatible with the current instance:
        i.e. with same set of subjects, each belonging to the same class.

        Parameters
        ----------
        dataset : Dataset or similar

        Returns
        -------
        compatible : bool
            Boolean flag indicating whether two datasets are compatible or not
        """

        compatible, _, _, _, _ = check_compatibility_BaseDataset([self, another])
        return compatible


    def summarize(self):
        """
        Summary of classes: names, numeric labels and sizes

        Returns
        -------
        tuple : target_set, label_set, target_sizes

        target_set : list
            List of names of all the classes

        target_sizes : list
            Size of each class (number of samples)

        """

        target_sizes = np.zeros(len(self.target_set))
        for idx, target in enumerate(self.target_set):
            target_sizes[idx] = self.target_sizes[target]

        return self.target_set, target_sizes


    def __str__(self):
        """Returns a concise and useful text summary of the dataset."""
        full_descr = list()
        if self.description not in [None, '']:
            full_descr.append(self.description)
        if bool(self):
            full_descr.append('{} samplets, {} targets, {} features'.format(
                    self.num_samplets, self.num_targets, self.num_features))
            class_ids = list(self.target_sizes)
            max_width = max([len(cls) for cls in class_ids])
            num_digit = max([len(str(val)) for val in self.target_sizes.values()])
            for cls in class_ids:
                full_descr.append(
                    'Class {cls:>{clswidth}} : '
                    '{size:>{numwidth}} samplets'.format(cls=cls, clswidth=max_width,
                                                        size=self.target_sizes.get(cls),
                                                        numwidth=num_digit))
        else:
            full_descr.append('Empty dataset.')

        return '\n'.join(full_descr)


    def __format__(self, fmt_str='s'):
        if fmt_str.lower() in ['', 's', 'short']:
            return '{} samplets x {} features each in {} classes'.format(
                    self.num_samplets, self.num_features, self.num_targets)
        elif fmt_str.lower() in ['f', 'full']:
            return self.__str__()
        else:
            raise NotImplementedError("Requsted type of format not implemented.\n"
                                      "It can only be 'short' (default) or 'full', "
                                      "or a shorthand: 's' or 'f' ")

    def __repr__(self):
        return self.__str__()

    # renaming the method for backwards compatibility
    def data_and_labels(self):
        warnings.warn(DeprecationWarning('data_and_labels() is convenient method to '
                                         'access data_and_targets() method.'
                                         'Switch to the latter ASAP.'))
        return self.data_and_targets()

