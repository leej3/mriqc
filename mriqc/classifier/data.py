#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: oesteban
# @Date:   2015-11-19 16:44:27

"""
===================
Data handler module
===================

Reads in and writes CSV files with the IQMs


"""
from __future__ import absolute_import, division, print_function, unicode_literals

import numpy as np
from statsmodels.robust.scale import mad
import pandas as pd
from builtins import str

from mriqc import logging
from mriqc.utils.misc import BIDS_COMP
LOG = logging.getLogger('mriqc.classifier')


def combine_datasets(inputs, rating_label='rater_1'):
    mdata = []
    for dataset_x, dataset_y, sitename in inputs:
        sitedata, _ = read_dataset(
            dataset_x, dataset_y, rate_label=rating_label,
            binarize=True, site_name=sitename)
        sitedata['database'] = [sitename] * len(sitedata)

        if sitename == 'DS030':
            sitedata['site'] = [sitename] * len(sitedata)

        mdata.append(sitedata)

    mdata = pd.concat(mdata)

    all_cols = mdata.columns.ravel().tolist()

    bids_comps = list(BIDS_COMP.keys())
    bids_comps_present = list(set(mdata.columns.ravel().tolist()) & set(bids_comps))
    bids_comps_present = [bit for bit in bids_comps if bit in bids_comps_present]

    ordered_cols = bids_comps_present + ['database', 'site', 'rater_1']
    ordered_cols += sorted(list(set(all_cols) - set(ordered_cols)))
    return mdata[ordered_cols]

def read_iqms(feat_file):
    """ Reads in the features """

    bids_comps = list(BIDS_COMP.keys())
    x_df = pd.read_csv(feat_file, index_col=False,
                       dtype={col: str for col in bids_comps})

    # Find present bids bits and sort by them
    bids_comps_present = list(set(x_df.columns.ravel().tolist()) & set(bids_comps))
    bids_comps_present = [bit for bit in bids_comps if bit in bids_comps_present]
    x_df = x_df.sort_values(by=bids_comps_present)

    # Remove sub- prefix in subject_id
    x_df.subject_id = x_df.subject_id.str.lstrip('sub-')

    # Remove columns that are not IQMs
    feat_names = list(x_df._get_numeric_data().columns.ravel())
    for col in bids_comps:
        try:
            feat_names.remove(col)
        except ValueError:
            pass

    for col in feat_names:
        if col.startswith(('size_', 'spacing_', 'Unnamed')):
            feat_names.remove(col)

    return x_df, feat_names, bids_comps_present

def read_labels(label_file, rate_label='rater_1', binarize=True,
                site_name=None):
    """ Reads in the labels """
    # Massage labels table to have the appropriate format

    bids_comps = list(BIDS_COMP.keys())

    y_df = pd.read_csv(label_file, index_col=False,
                       dtype={col: str for col in bids_comps})

    # Find present bids bits and sort by them
    bids_comps_present = list(set(y_df.columns.ravel().tolist()) & set(bids_comps))
    bids_comps_present = [bit for bit in bids_comps if bit in bids_comps_present]
    y_df = y_df.sort_values(by=bids_comps_present)
    y_df.subject_id = y_df.subject_id.str.lstrip('sub-')

    # Convert string labels to ints
    try:
        y_df.loc[y_df[rate_label].str.contains('fail', case=False, na=False), rate_label] = -1
        y_df.loc[y_df[rate_label].str.contains('exclude', case=False, na=False), rate_label] = -1
        y_df.loc[y_df[rate_label].str.contains('maybe', case=False, na=False), rate_label] = 0
        y_df.loc[y_df[rate_label].str.contains('may be', case=False, na=False), rate_label] = 0
        y_df.loc[y_df[rate_label].str.contains('ok', case=False, na=False), rate_label] = 1
        y_df.loc[y_df[rate_label].str.contains('good', case=False, na=False), rate_label] = 1
    except AttributeError:
        pass

    y_df[[rate_label]] = y_df[[rate_label]].apply(pd.to_numeric, errors='raise')

    if binarize:
        y_df.loc[y_df[rate_label] >= 0, rate_label] = 0
        y_df.loc[y_df[rate_label] < 0, rate_label] = 1


    add_cols = [rate_label]
    # Set default name
    if 'site' in y_df.columns.ravel().tolist():
        add_cols.insert(0, 'site')
    elif site_name is not None:
        y_df['site'] = [site_name] * len(y_df)
        add_cols.insert(0, 'site')

    return y_df[bids_comps_present + add_cols]


def read_dataset(feat_file, label_file, rate_label='rater_1', merged_name=None,
                 binarize=True, site_name=None):
    """ Reads in the features and labels """

    x_df, feat_names, _ = read_iqms(feat_file)
    y_df = read_labels(label_file, rate_label, binarize,
                       site_name=site_name)

    # Find present bids bits and sort by them
    bids_comps = list(BIDS_COMP.keys())
    bids_comps_x = list(set(x_df.columns.ravel().tolist()) & set(bids_comps))
    bids_comps_x = [bit for bit in bids_comps if bit in bids_comps_x]
    bids_comps_y = list(set(x_df.columns.ravel().tolist()) & set(bids_comps))
    bids_comps_y = [bit for bit in bids_comps if bit in bids_comps_y]

    if bids_comps_x != bids_comps_y:
        raise RuntimeError('Labels and features cannot be merged')

    x_df['bids_ids'] = x_df.subject_id.values.copy()
    y_df['bids_ids'] = y_df.subject_id.values.copy()

    for comp in bids_comps_x[1:]:
        x_df['bids_ids'] = x_df.bids_ids.str.cat(x_df.loc[:, comp].astype(str), sep='_')
        y_df['bids_ids'] = y_df.bids_ids.str.cat(y_df.loc[:, comp].astype(str), sep='_')

    # Remove failed cases from Y, append new columns to X
    y_df = y_df[y_df['bids_ids'].isin(list(x_df.bids_ids.values.ravel()))]

    # Drop indexing column
    del x_df['bids_ids']
    del y_df['bids_ids']

    # Merge Y dataframe into X
    x_df = pd.merge(x_df, y_df, on=bids_comps_x, how='left')

    if merged_name is not None:
        x_df.to_csv(merged_name, index=False)

    # Drop samples with invalid rating
    nan_labels = x_df[x_df[rate_label].isnull()].index.ravel().tolist()
    if nan_labels:
        LOG.info('Dropping %d samples for having non-numerical '
                 'labels', len(nan_labels))
        x_df = x_df.drop(nan_labels)

    # Print out some info
    nsamples = len(x_df)
    LOG.info('Created dataset X="%s", Y="%s" (N=%d valid samples)',
             feat_file, label_file, nsamples)


    # Inform about ratings distribution
    labels = sorted(list(set(x_df[rate_label].values.ravel().tolist())))
    ldist = []
    for l in labels:
        ldist.append(int(np.sum(x_df[rate_label] == l)))

    LOG.info('Ratings distribution: %s (%s, %s)',
             '/'.join(['%d' % x for x in ldist]),
             '/'.join(['%.2f%%' % (100 * x / nsamples) for x in ldist]),
             'accept/exclude' if len(ldist) == 2 else 'exclude/doubtful/accept')

    return x_df, feat_names

def balanced_leaveout(dataframe, site_column='site', rate_label='rater_1'):
    sites = list(set(dataframe[[site_column]].values.ravel()))
    pos_draw = []
    neg_draw = []

    for site in sites:
        site_x = dataframe.loc[dataframe[site_column].str.contains(site)]
        site_x_pos = site_x[site_x[rate_label] == 1]

        if len(site_x_pos) > 4:
            pos_draw.append(np.random.choice(site_x_pos.index.tolist()))

            site_x_neg = site_x[site_x[rate_label] == 0]
            neg_draw.append(np.random.choice(site_x_neg.index.tolist()))

    left_out = dataframe.iloc[pos_draw + neg_draw].copy()
    dataframe = dataframe.drop(dataframe.index[pos_draw + neg_draw])
    return dataframe, left_out



def zscore_dataset(dataframe, excl_columns=None, by='site',
                   njobs=-1):
    """ Returns a dataset zscored by the column given as argument """
    from multiprocessing import Pool, cpu_count

    LOG.info('z-scoring dataset ...')

    if njobs <= 0:
        njobs = cpu_count()

    sites = list(set(dataframe[[by]].values.ravel().tolist()))
    columns = list(dataframe.select_dtypes([np.number]).columns.ravel())

    if excl_columns is None:
        excl_columns = []

    for col in columns:
        if not np.isfinite(np.sum(dataframe[[col]].values.ravel())):
            excl_columns.append(col)

    if excl_columns:
        for col in excl_columns:
            try:
                columns.remove(col)
            except ValueError:
                pass

    zs_df = dataframe.copy()

    pool = Pool(njobs)
    args = [(zs_df, columns, s) for s in sites]
    results = pool.map(zscore_site, args)
    for site, res in zip(sites, results):
        zs_df.loc[zs_df.site == site, columns] = res

    zs_df.replace([np.inf, -np.inf], np.nan)
    nan_columns = zs_df.columns[zs_df.isnull().any()].tolist()

    if nan_columns:
        LOG.warn('Columns %s contain NaNs after z-scoring.', ", ".join(nan_columns))
        zs_df[nan_columns] = dataframe[nan_columns].values

    return zs_df

def zscore_site(args):
    """ z-scores only one site """
    from scipy.stats import zscore
    dataframe, columns, site = args
    return zscore(dataframe.loc[dataframe.site == site, columns].values,
                  ddof=1, axis=0)


def find_gmed(dataframe, by='site', excl_columns=None):
    sites = list(set(dataframe[[by]].values.ravel().tolist()))
    numcols = dataframe.select_dtypes([np.number]).columns.ravel().tolist()

    if excl_columns:
        numcols = [col for col in numcols if col not in excl_columns]

    LOG.info('Calculating bias of dataset (%d features)', len(numcols))

    site_medians = []
    for site in sites:
        site_medians.append(np.median(dataframe.loc[dataframe.site == site, numcols], axis=0))

    return np.median(np.array(site_medians), axis=0)


def norm_gmed(dataframe, grand_medians, by='site', excl_columns=None):
    LOG.info('Removing bias of dataset ...')

    all_cols = dataframe.columns.ravel().tolist()
    if by not in all_cols:
        dataframe[by] = ['Unknown'] * len(dataframe)

    sites = list(set(dataframe[[by]].values.ravel().tolist()))
    numcols = dataframe.select_dtypes([np.number]).columns.ravel().tolist()

    if excl_columns:
        numcols = [col for col in numcols if col not in excl_columns]

    for site in sites:
        vals = dataframe.loc[dataframe.site == site, numcols]
        site_med = np.median(vals, axis=0)
        dataframe.loc[dataframe.site == site, numcols] = vals - site_med + grand_medians

    return dataframe


def find_iqrs(dataframe, by='site', excl_columns=None):
    sites = list(set(dataframe[[by]].values.ravel().tolist()))
    numcols = dataframe.select_dtypes([np.number]).columns.ravel().tolist()

    if excl_columns:
        numcols = [col for col in numcols if col not in excl_columns]

    LOG.info('Calculating IQR of dataset (%d)', len(numcols))

    meds = []
    iqrs = []
    for site in sites:
        vals = dataframe.loc[dataframe.site == site, numcols]
        iqrs.append(mad(vals, axis=0))
        meds.append(np.median(vals, axis=0))

    return [np.median(np.array(meds), axis=0),
            np.median(np.array(iqrs), axis=0)]


def norm_iqrs(dataframe, mean_iqr, by='site', excl_columns=None):
    LOG.info('Removing bias of dataset ...')

    all_cols = dataframe.columns.ravel().tolist()
    if by not in all_cols:
        dataframe[by] = ['Unknown'] * len(dataframe)

    sites = list(set(dataframe[[by]].values.ravel().tolist()))
    numcols = dataframe.select_dtypes([np.number]).columns.ravel().tolist()

    if excl_columns:
        numcols = [col for col in numcols if col not in excl_columns]

    for site in sites:
        vals = dataframe.loc[dataframe.site == site, numcols]
        vals -= np.median(vals, axis=0)
        iqr = np.percentile(vals, 75, axis=0) - np.percentile(vals, 25, axis=0)
        vals.iloc[:, iqr > 1.e-5] *= (1.0 / iqr[iqr > 1.e-5])
        changecols = vals.iloc[:, iqr > 1.e-5].columns.ravel().tolist()
        dataframe.loc[dataframe.site == site, changecols] = vals

    return dataframe
