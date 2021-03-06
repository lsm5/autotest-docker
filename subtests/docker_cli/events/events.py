r"""
Summary
----------

Start up a simple ``/bin/true`` container while monitoring
output from ``docker events`` command.  Verify expected events
appear after container finishes and is removed.

Operational Summary
----------------------

#. Listen for events
#. Run /bin/true container
#. Check parsing of events and container events present

Prerequisites
---------------------------------------------
*  Historical events exist prior to running test (i.e.
   docker daemon hasn't been restarted in a while)
*  Host clock is accurate, local timezone setup properly.
*  Host clock does not change drastically during test
"""

import re
from string import Template
import time
from dockertest.subtest import Subtest
from dockertest.output import DockerTime
from dockertest.containers import DockerContainers
from dockertest.images import DockerImage
from dockertest.dockercmd import DockerCmd
from dockertest.output import mustpass
from dockertest.dockercmd import AsyncDockerCmd
from dockertest.xceptions import DockerValueError


cid_regex = re.compile(r'\s+([a-z0-9]{64})\:\s+')
fqin_regex = DockerImage.repo_split_p
source_regex = re.compile(r'\s+\(from\s+\S+\)\s+')
operation_regex = re.compile(r'\s+(\w+)$')  # final word chars


def event_dt(line):
    try:
        return DockerTime(line)
    except (AttributeError, TypeError, ValueError):  # failed
        return None


def event_cid(line):
    mobj = cid_regex.search(line)
    if mobj is not None:
        return mobj.group(1)
    else:
        return None


def event_fqin(line):
    mobj = fqin_regex.search(line)
    if mobj is not None:
        return mobj.group(0)
    else:
        return None


def event_source(line):
    mobj = source_regex.search(line)
    if mobj is not None:
        # Verifies formatting
        containerid = "".join([s for s in mobj.group(0)
                               if s is not None])
        return containerid
    else:
        return None


def event_operation(line):
    mobj = operation_regex.search(line)
    if mobj is not None:
        return mobj.group(1)
    else:
        return None


def event_details(line):
    return {'datetime': event_dt(line),
            'source': event_source(line),
            'operation': event_operation(line)}


def is_dupe_event(needle, haystack):
    for event in haystack:
        # Fastest comparison order
        if (needle['datetime'] == event['datetime'] and
                needle['source'] == event['source'] and
                needle['operation'] == event['operation']):
            return True
    return False


def parse_event(line):
    """
    Return tuple(CID/FQIN, {DETAILS}) from parsing line

    :param line: String-like containing a single event line
    :returns: (CID/FQIN, {DETAILS}) from parsing line or None if unparseable
    """
    identifier = event_cid(line)
    if identifier is None:
        identifier = event_fqin(line)
    details = event_details(line)
    if identifier is None or details['datetime'] is None:
        return None  # unparseable line
    else:
        return (identifier, details)


def parse_events(lines, slop=None):
    """
    Return list of tuples for valid lines returned by parse_events()

    :param lines: String containing events, one per line
    :param slop: number of unparseable lines to tollerate, None/- to disable
    :returns: List of tuple(CID, {DETAILS}) as returned from parse_events()
    """
    sloppy = []
    result = []
    n_lines = 0
    for line in lines.splitlines():
        n_lines += 1
        if len(line) < 64:   # len of a cid
            sloppy.append(line)
            continue
        cid_details = parse_event(line)
        if cid_details is not None:
            result.append(cid_details)
        else:
            sloppy.append(line)
        if slop is not None and slop >= 0:
            n_slop = len(sloppy)
            if n_slop > slop:
                raise DockerValueError("Excess slop (>%d) encountered after "
                                       "parsing (%d) events (success on %d). "
                                       " Garbage: %s"
                                       % (slop, n_lines, n_lines - n_slop,
                                          sloppy))
    return result


def events_by_id(events_list, previous=None):
    """
    Return a dictionary, mapping of CID or FQIN to de-duplicated details list

    :param events_list: List of tuple(CID/FQIN, {DETAILS}) from parse_events()
    :param previous: Possibly overlapping prior result from events_by_id()
    :returns: dict-like mapping CID/FQIN to de-duplicated event-details list
    """
    if previous is None:
        dct = {}
    else:
        dct = previous  # in-place update
    for _id, details in events_list:
        previous_events = dct.get(_id)
        if previous_events is None:
            previous_events = dct[_id] = []  # in-place update (below)
        if not is_dupe_event(details, previous_events):
            # don't assume it belongs at end
            previous_events.append(details)
            # using key is faster then custom compare function
            previous_events.sort(key=lambda details: details['datetime'])
    return dct  # possibly same as previous


class events(Subtest):
    config_section = 'docker_cli/events'

    def initialize(self):
        super(events, self).initialize()
        dc = self.stuff['dc'] = DockerContainers(self)
        fullname = dc.get_unique_name()
        fqin = DockerImage.full_name_from_defaults(self.config)
        # generic args have spots for some value substitution
        mapping = {'NAME': fullname, 'IMAGE': fqin}
        subargs = []
        for arg in self.config['run_args'].strip().split(','):
            tmpl = Template(arg)
            # Ignores placeholders not in mapping
            subargs.append(tmpl.safe_substitute(mapping))
        # test container executed later
        self.stuff['nfdc'] = DockerCmd(self, 'run', subargs)
        self.stuff['nfdc_cid'] = None
        # docker events command executed later
        events_cmd = AsyncDockerCmd(self, 'events', ['--since=0'])
        self.stuff['events_cmd'] = events_cmd
        self.stuff['events_cmdresult'] = None
        # These will be removed as expected events for cid are identified
        leftovers = self.config['expect_events'].strip().split(',')
        self.stuff['leftovers'] = leftovers
        for key, value in self.stuff.items():
            self.logdebug("init %s = %s", key, value)

    def run_once(self):
        super(events, self).run_once()
        dc = self.stuff['dc']
        # Start listening
        self.stuff['events_cmd'].execute()
        # Do something to make new events
        cmdresult = mustpass(self.stuff['nfdc'].execute())
        cid = self.stuff['nfdc_cid'] = cmdresult.stdout.strip()
        while True:
            _json = dc.json_by_long_id(cid)
            if len(_json) > 0 and _json[0]["State"]["Running"]:
                self.loginfo("Waiting for test container to exit...")
                time.sleep(3)
            else:
                break
        if self.config['rm_after_run']:
            self.loginfo("Removing test container...")
            try:
                dc.kill_container_by_long_id(cid)
            except ValueError:
                pass  # container isn't running, this is fine.
            dcmd = DockerCmd(self, 'rm', ['--force', '--volumes', cid])
            mustpass(dcmd.execute())
        # No way to know how long async events take to pass through :S
        self.loginfo("Sleeping %s seconds for events to catch up",
                     self.config['wait_stop'])
        time.sleep(self.config['wait_stop'])
        # Kill off docker events after 1 second
        events_cmd = self.stuff['events_cmd']
        self.stuff['events_cmdresult'] = events_cmd.wait(timeout=1)

    def postprocess(self):
        super(events, self).postprocess()
        stdout = self.stuff['events_cmdresult'].stdout.strip()
        # one-line (about) minimum
        self.failif(len(stdout) < 80, "Output too short: '%s'" % stdout)
        all_events = parse_events(stdout)
        cid_events = events_by_id(all_events)
        cid = self.stuff['nfdc_cid']
        self.failif(cid not in cid_events,
                    'Test container cid %s does not appear in events' % cid)
        test_events = cid_events[cid]
        for event in test_events:
            if event['operation'] in self.stuff['leftovers']:
                self.stuff['leftovers'].remove(event['operation'])
            else:
                self.logwarning("Untested event: %s", event)
        self.failif(len(self.stuff['leftovers']) > 0,
                    "Expected event operation(s) %s for cid %s not found"
                    % (self.stuff['leftovers'], self.stuff['nfdc_cid']))
        self.loginfo("All expected events were located")
        # Fail test if too much unparseable garbage
        all_events = parse_events(stdout,
                                  self.config['unparseable_allowance'])

    def cleanup(self):
        super(events, self).cleanup()
        if self.config['remove_after_test']:
            cid = self.stuff['nfdc_cid']
            DockerCmd(self, 'rm', ['--force', '--volumes', cid]).execute()
