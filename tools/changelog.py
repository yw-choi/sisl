#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# -*- encoding:utf-8 -*-
"""
Script to generate contributor and pull request lists

This script generates contributor and pull request lists for release
changelogs using Github v3 protocol. Use requires an authentication token in
order to have sufficient bandwidth, you can get one following the directions at
`<https://help.github.com/articles/creating-an-access-token-for-command-line-use/>_
Don't add any scope, as the default is read access to public information. The
token may be stored in an environment variable as you only get one chance to
see it.

Usage::

    $ ./tools/changelog.py <token> <revision range>

The output is utf8 rst.

Dependencies
------------

- gitpython
- pygithub

Some code was copied from scipy `tools/gh_list.py` and `tools/authors.py`.

Examples
--------

From the bash command line with $GITHUB token::

    $ ./tools/changelog.py $GITHUB v1.13.0..v1.14.0 > 1.14.0-changelog.rst

"""
import os
import sys
import re
import datetime
from git import Repo
from github import Github

if sys.version_info[:2] < (3, 6):
    raise RuntimeError("Python version must be >= 3.6")

this_repo = Repo(os.path.join(os.path.dirname(__file__), ".."))

author_msg = """
A total of %d people contributed to this release.  People with a "+" by their
names contributed a patch for the first time.
"""

pull_request_msg = """
A total of %d pull requests were merged for this release.
"""


def get_authors(revision_range):
    pat = "^.*\\t(.*)$"
    lst_release, cur_release = [r.strip() for r in revision_range.split("..")]

    # authors, in current release and previous to current release.
    cur = set(re.findall(pat, this_repo.git.shortlog("-s", revision_range), re.M))
    pre = set(re.findall(pat, this_repo.git.shortlog("-s", lst_release), re.M))

    # Homu is the author of auto merges, clean him out.
    cur.discard("Homu")
    pre.discard("Homu")

    # Append '+' to new authors.
    authors = [s + " +" for s in cur - pre] + [s for s in cur & pre]
    authors.sort()
    return authors


def get_pull_requests(repo, revision_range):
    prnums = []

    # From regular merges
    merges = this_repo.git.log("--oneline", "--merges", revision_range)
    issues = re.findall("Merge pull request \\#(\\d*)", merges)
    prnums.extend(int(s) for s in issues)

    # From Homu merges (Auto merges)
    issues = re.findall("Auto merge of \\#(\\d*)", merges)
    prnums.extend(int(s) for s in issues)

    # From fast forward squash-merges
    commits = this_repo.git.log(
        "--oneline", "--no-merges", "--first-parent", revision_range
    )
    issues = re.findall("^.*\\(\\#(\\d+)\\)$", commits, re.M)
    prnums.extend(int(s) for s in issues)

    # get PR data from github repo
    prnums.sort()
    prs = [repo.get_pull(n) for n in prnums]
    return prs

def read_changelog(prior_rel, current_rel, format="md"):
    # rst search for item
    md_item = re.compile(r"^\s*-")

    # when to capture the content
    print_out = False
    # for getting the date
    date = None
    out = []
    for line in open("../CHANGELOG.md", 'r'):
        if f"## [{current_rel}]" in line:
            print_out = True
            date = line.split("-", 1)[1].strip()
            continue
        elif f"## [{prior_rel}]" in line:
            break
        elif not print_out:
            continue

        header = 0
        if format == "md":
            # no change in header lines
            pass
        elif format == "rst":
            if line.startswith("###"):
                header = 3
            elif line.startswith("##"):
                header = 2
            elif line.startswith("#"):
                header = 1
            elif md_item.search(line):
                line = line.replace("-", "*", 1)

            if header > 0:
                line = line[header:].lstrip()
        out.append(line)

        if header > 0:
            # this will only happen for rst
            n = len(line)
            out.append((" =-^"[header]) * n + "\n")

    # parse the date into an iso date
    if date is not None:
        date = datetime.date(*[int(x) for x in date.split("-")])
        date = date.strftime("%d of %B %Y")
        if date[0] == "0":
            date = date[1:]
            
    return "".join(out).strip(), date

def main(token, revision_range, format="md"):
    prior_rel, current_rel = [r.strip() for r in revision_range.split("..")]

    # Also add the CHANGELOG.md information
    if prior_rel.startswith("v"):
        prior_rel = prior_rel[1:]

    current_version = current_rel
    if current_rel.startswith("v"):
        current_rel = current_rel[1:]
        current_version = current_rel
    elif cur_release == "HEAD":
        current_rel = "Unreleased"
        current_version = "TBD"

    changelog, date = read_changelog(prior_rel, current_rel, format=format)

    if format == "rst" and current_version != "TBD":
        print("*" * len(current_version))
        print(current_version)
        print("*" * len(current_version))

    # print date
    if date is not None:
        print(f"\nReleased {date}.\n")

    github = Github(token)
    github_repo = github.get_repo("zerothi/sisl")

    # document authors
    authors = get_authors(revision_range)
    heading = "Contributors"
    print(f"\n{heading}")
    print("=" * len(heading))
    print(author_msg % len(authors))

    for s in authors:
        print("* " + s)

    # document pull requests
    pull_requests = get_pull_requests(github_repo, revision_range)
    heading = "Pull requests merged"
    pull_msg = "* #{0}: {2}"

    print(f"\n{heading}")
    print("=" * len(heading))
    print(pull_request_msg % len(pull_requests))

    for pull in pull_requests:
        title = re.sub("\\s+", " ", pull.title.strip())
        if len(title) > 60:
            remainder = re.sub("\\s.*$", "...", title[60:])
            if len(remainder) > 20:
                title = title[:80] + "..."
            else:
                title = title[:60] + remainder
        print(pull_msg.format(pull.number, pull.html_url, title))

    if len(changelog) > 0:
        print()
        print(changelog)


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Generate author/pr lists for release")
    parser.add_argument("--format", choices=("md", "rst"), help="which format to write out in")
    parser.add_argument("token", help="github access token")
    parser.add_argument("revision_range", help="<revision>..<revision>")
    args = parser.parse_args()
    main(args.token, args.revision_range, format=args.format)
