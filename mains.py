#!/usr/bin/python
# -*- coding: utf-8 -*-

# Analytics API:
# https://developers.google.com/analytics/devguides/reporting/core/v3/reference

__author__ = ['api.nickm@gmail.com (Nick Mihailovski)',
              'Luke Skibinski <l.skibinski@elifesciences.org>']

from collections import Counter
import re, sys, argparse
from datetime import datetime, timedelta
from pprint import pprint

from apiclient.errors import HttpError
from apiclient import sample_tools
from oauth2client.client import AccessTokenRefreshError

# Declare command-line flags.
argparser = argparse.ArgumentParser(add_help=False)
argparser.add_argument('table_id', type=str,
                     help=('The table ID of the profile you wish to access. '
                           'Format is ga:xxx where xxx is your profile ID.'))

def ymd(dt):
    return dt.strftime("%Y-%m-%d")

def event_counts(service, table_id, from_date, to_date):
    "returns the raw GA results for PDF downloads between the two given dates"
    assert isinstance(from_date, datetime), "'from' date must be a datetime object. received %r" % from_date
    assert isinstance(to_date, datetime), "'to' date must be a datetime object. received %r" % to_date
    
    return service.data().ga().get(
        ids = table_id,
        max_results=10000, # 10,000 is the max GA will ever return
        start_date = ymd(from_date),
        end_date = ymd(to_date),
        metrics = 'ga:totalEvents',
        dimensions = 'ga:eventLabel',
        sort = '-ga:totalEvents',
        # ';' separates AND expressions, ',' separates OR expressions
        filters = r'ga:eventAction==Download;ga:eventCategory==Article;ga:eventLabel=~pdf-article',
    )

def download_counts(row_list):
    def parse(row):
        label, count = row
        return label.split('::')[0], count
    return dict(map(parse, row_list))

def path_counts(service, table_id, from_date, to_date):
    "returns the raw GA results for article page views between the two given dates"
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
    
    return service.data().ga().get(
        ids = table_id,
        max_results=10000, # 10,000 is the max GA will ever return
        start_date = ymd(from_date),
        end_date = ymd(to_date),
        metrics = 'ga:pageviews',
        dimensions = 'ga:pagePath',
        #dimensions='ga:url,ga:keyword',
        sort = '-ga:pageviews',
        #filters = 'ga:pagePath=~/e[0-9]+((\.full)?|(\.abstract)|(\.abstract-2)(/abstract))?$',
        filters = r'ga:pagePath=~/e[0-9]+(%s)$' % suffix_str,
    )

def article_counts(path_count_pairs):
    """takes raw path data from GA and groups by article, returning a
    list of (artid, full-count, abstract-count, digest-count)"""

    type_map = {
        None: 'full',
        'full': 'full',
        'abstract': 'abstract',
        'short': 'abstract',
        'abstract-1': 'abstract',
        'abstract-2': 'digest'
    }
    splitter = re.compile('\.|/')

    def article_count(pair):
        "figures out the type of the given path using the suffix (if one available)"
        try:
            bits = pair[0].split('/', 3)
            art = bits[-1]
            more_bits = re.split(splitter, art, maxsplit=1)
            suffix = None
            if len(more_bits) > 1:
                art, suffix = more_bits
            assert suffix in type_map, "unknown suffix %r! received: %r split to %r" % (suffix, pair, more_bits)
            return art, type_map[suffix], int(pair[1])
        except AssertionError:
            # we have a weird path
            print 'bar row:',pair
            return []
            

    # for each path, build a list of path_type: value
    article_groups = {}
    for pair in path_count_pairs:
        row = Counter({
            'full': 0,
            'abstract': 0,
            'digest': 0,
        })
        triplet = article_count(pair)
        if not len(triplet) == 3:
            continue # bad row
        art, art_type, count = triplet
        group = article_groups.get(art, [row])
        group.append(Counter({art_type: count}))
        article_groups[art] = group

    # take our list of Counter objects and count them up
    def update(a,b):
        # https://docs.python.org/2/library/collections.html#collections.Counter.update
        a.update(b)
        return a
    return {art: reduce(update, group) for art, group in article_groups.items()}    


def query_ga(q):
    # Try to make a request to the API. Print the results or handle errors.
    try:
        return q.execute()
            
    except TypeError, error:      
        # Handle errors in constructing a query.
        print ('There was an error in constructing your query : %s' % error)
        raise

    except HttpError, error:
        # Handle API errors.
        print ('Arg, there was an API error : %s : %s' %
               (error.resp.status, error._get_reason()))
        raise

    except AccessTokenRefreshError:
        # Handle Auth errors.
        print ('The credentials have been revoked or expired, please re-run '
               'the application to re-authorize')
        raise    


#
# bootstrap
#

def main(argv):
    """has to be called with the 'table-id', which looks like 12345678
    call this app like: python mains.py 'ga:12345678'"""
    
    # Authenticate and construct service.
    service, flags = sample_tools.init(
      argv, 'analytics', 'v3', __doc__, __file__, parents=[argparser],
      scope='https://www.googleapis.com/auth/analytics.readonly')

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    view_results = query_ga(event_counts(service, flags.table_id, yesterday, today))
    download_results = query_ga(path_counts(service, flags.table_id, yesterday, today))

    return {'views': download_counts(view_results['rows']),
            'downloads': article_counts(download_results['rows'])}

if __name__ == '__main__':
    pprint(main(sys.argv))
