#!/usr/bin/python
# -*- coding: utf-8 -*-

# Analytics API:
# https://developers.google.com/analytics/devguides/reporting/core/v3/reference

__author__ = [
    'Luke Skibinski <l.skibinski@elifesciences.org>',
]

import os, re
from os.path import join
from collections import Counter
from datetime import datetime
from elife_ga_metrics import utils
from elife_ga_metrics.utils import ymd
import logging

#from elife_ga_metrics import core # can't be doing this, circular dependencies.

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.level = logging.INFO

#
# downloads handling
#

def event_counts_query(table_id, from_date, to_date):
    "returns the raw GA results for PDF downloads between the two given dates"
    assert isinstance(from_date, datetime), "'from' date must be a datetime object. received %r" % from_date
    assert isinstance(to_date, datetime), "'to' date must be a datetime object. received %r" % to_date
    return {
        'ids': table_id,
        'max_results': 10000, # 10,000 is the max GA will ever return
        'start_date': ymd(from_date),
        'end_date': ymd(to_date),
        'metrics': 'ga:totalEvents',
        'dimensions': 'ga:eventLabel',
        'sort': 'ga:eventLabel',
        # ';' separates 'AND' expressions, ',' separates 'OR' expressions
        'filters': r'ga:eventAction==Download;ga:eventCategory==Article;ga:eventLabel=~pdf-article',
    }

def event_counts(row_list):
    "parses the list of rows returned by google to extract the doi and it's count"
    def parse(row):
        label, count = row
        return label.split('::')[0], int(count)
    return dict(map(parse, row_list))

#
# views handling
#

def path_counts_query(table_id, from_date, to_date):
    """returns a GA query object that, when executed, returns raw
    results for article page views between the two given dates"""
    assert isinstance(from_date, datetime), "'from' date must be a datetime object. received %r" % from_date
    assert isinstance(to_date, datetime), "'to' date must be a datetime object. received %r" % to_date

    # regular expression suffixes (escape special chars)
    suffix_list = [
        '\.full',
        '\.abstract',
        '\.short',
        '/abstract-1',
        '/abstract-2',
    ]
    # wrap each suffix in a zero-or-one group. ll: ['(\.full)?', '(\.abstract)?', ...]
    suffix_list = ['(%s)?' % suffix for suffix in suffix_list]

    # pipe-delimit the suffix list. ll: '(\.full)?|(\.abstract)?|...)'
    suffix_str = '|'.join(suffix_list)
    
    return {
        'ids': table_id,
        'max_results': 10000, # 10,000 is the max GA will ever return
        'start_date': ymd(from_date),
        'end_date': ymd(to_date),
        'metrics': 'ga:pageviews',
        'dimensions': 'ga:pagePath',
        'sort': 'ga:pagePath',
        'filters': ','.join([
            # these filters are OR'ed
            r'ga:pagePath=~^/content/.*/e[0-9]{5}(%s)$' % suffix_str,
            r'ga:pagePath=~^/content/.*/elife\.[0-9]{5}$',
        ])
    }

# wrangling of the response from the above

TYPE_MAP = {
    None: 'full',
    'full': 'full',
    'abstract': 'abstract',
    'short': 'abstract',
    'abstract-1': 'abstract',
    'abstract-2': 'digest'
}
SPLITTER = re.compile('\.|/')

def path_count(pair):
    "figures out the type of the given path using the suffix (if one available)"
    try:
        if pair[0].lower().startswith('/content/early/'):
            # handles POA article variation 1 "/content/early/yyyy/mm/dd/doi/" type urls
            bits = pair[0].split('/', 6)
            bits[-1] = utils.deplumpen(bits[-1])

        elif pair[0].lower().startswith('/content/elife/early/'):
            # handles POA article variation 2 "/content/elife/early/yyyy/mm/dd/doi/" type urls
            bits = pair[0].split('/', 7)
            bits[-1] = utils.deplumpen(bits[-1])

        elif pair[0].lower().startswith('/content/elife/'):
            # handles valid but unsupported /content/elife/volume/id paths
            # these paths appear in PDF files I've been told
            bits = pair[0].split('/', 4)
            
        else:
            # handles standard /content/volume/id/ paths
            bits = pair[0].split('/', 3)
        
        art = bits[-1]
        art = art.lower() # website isn't case sensitive, we are
        more_bits = re.split(SPLITTER, art, maxsplit=1)
        
        suffix = None
        if len(more_bits) > 1:
            art, suffix = more_bits
        assert suffix in TYPE_MAP, "unknown suffix %r! received: %r split to %r" % (suffix, pair, more_bits)
        return art, TYPE_MAP[suffix], int(pair[1])

    except AssertionError, e:
        # we have an unhandled path
        #LOG.warn("skpping unhandled path %s (%r)", pair, e)
        LOG.warn("skpping unhandled path %s", pair)

def path_counts(path_count_pairs):
    """takes raw path data from GA and groups by article, returning a
    list of (artid, full-count, abstract-count, digest-count)"""
    
    # for each path, build a list of path_type: value
    article_groups = {}
    for pair in path_count_pairs:
        row = Counter({
            'full': 0,
            'abstract': 0,
            'digest': 0,
        })
        triplet = path_count(pair)
        if not triplet:
            continue # skip bad row
        art, art_type, count = triplet
        group = article_groups.get(art, [row])
        group.append(Counter({art_type: count}))
        article_groups[art] = group

    # take our list of Counter objects and count them up
    def update(a,b):
        # https://docs.python.org/2/library/collections.html#collections.Counter.update
        a.update(b)
        return a

    return {utils.enplumpen(art): reduce(update, group) for art, group in article_groups.items()}    
