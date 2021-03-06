"""
Adapt/extend autotest.client.test.test for Docker test sub-framework
Implement docker subtest base to avoid circular dependences in dockertest core
modules.
"""

# Pylint runs from a different directory, it's fine to import this way
# pylint: disable=W0403

import logging
import traceback
from xceptions import DockerTestFail
from config import get_as_list


class SubBase(object):

    """
    Methods/attributes common to Subtest & SubSubtest classes

    :note: This class is indirectly referenced by the control-file
           so it cannot contain anything dockertest-implementation
           specific.
    """

    #: Configuration section for subclass, auto-generated by ``__init__``.
    config_section = None

    #: Configuration dictionary (read-only for instances)
    config = None

    #: Unique temporary directory for this instance (automatically cleaned up)
    #: **warning**: DO NOT ASSUME DIRECTORY WILL BE EMPTY!!!
    tmpdir = None

    #: Number of additional space/tab characters to prefix when logging
    n_spaces = 16  # date/timestamp length

    #: Number of additional space/tab characters to prefix when logging
    n_tabs = 1     # one-level

    step_log_msgs = {
        "initialize": "initialize()",
        "run_once": "run_once()",
        "postprocess": "postprocess()",
        "cleanup": "cleanup()"
    }

    def __init__(self, *args, **dargs):
        super(SubBase, self).__init__(*args, **dargs)
        self.step_log_msgs = self.step_log_msgs.copy()

    def initialize(self):
        """
        Called every time the test is run.
        """
        self.log_step_msg('initialize')
        # Issue warnings for failed to customize suggested options
        not_customized = self.config.get('__example__', None)
        if not_customized is not None and not_customized is not '':
            self.logdebug("WARNING: Recommended options not customized:")
            for nco in get_as_list(not_customized):
                self.logdebug("WARNING: %s" % nco)
            self.logwarning("WARNING: Test results may be externally "
                            "dependent! (See debug log for details)")
        msg = "%s configuration:\n" % self.__class__.__name__
        for key, value in self.config.items():
            if key == '__example__' or key.startswith('envcheck'):
                continue
            msg += '\t\t%s = "%s"\n' % (key, value)
        self.logdebug(msg)

    def run_once(self):
        """
        Called once only to exercise subject of sub-subtest
        """
        self.log_step_msg('run_once')

    def postprocess(self):
        """
        Called to process results of subject
        """
        self.log_step_msg('postprocess')

    def cleanup(self):
        """
        Always called, before any exceptions thrown are re-raised.
        """
        self.log_step_msg('cleanup')

    def log_step_msg(self, stepname):
        """
        Send message stored in ``step_log_msgs`` key ``stepname`` to logingo
        """
        msg = self.step_log_msgs.get(stepname)
        if msg:
            self.loginfo(msg)

    @staticmethod
    def failif(condition, reason=None):
        """
        Convenience method for subtests to avoid importing ``TestFail``
        exception

        :param condition: Boolean condition, fail test if True.
        :param reason: Helpful text describing why the test failed
        :raise DockerTestFail: If condition evaluates ``True``
        """

        if reason is None:
            reason = "Failed test condition"
        if bool(condition):
            raise DockerTestFail(reason)

    @classmethod
    def log_x(cls, lvl, msg, *args):
        """
        Send ``msg`` & ``args`` through to logging module function with
        name ``lvl``
        """

        meth = getattr(logging, lvl)
        testname = cls.__name__
        return meth("%s%s: %s" % ("\t" * cls.n_tabs, testname, msg), *args)

    @classmethod
    def log_xn(cls, lvl, msg, *args):
        """
        Multiline-split and send msg & args through to logging module

        :param lvl: logging method name (``'debug'``, ``'info'``, etc.)
        :param msg: Message format-string
        """
        # date, loglevel, this module offset
        newline = '\n' + ' ' * cls.n_spaces + '\t' * cls.n_tabs
        newline += " " * (len(cls.__name__) + 2)    # cls name + ': '
        try:
            msg = (str(msg) % args).replace('\n', newline)
        except TypeError:
            if args is tuple():
                cls.logwarning("Following message contains format strings but "
                               "has no arguments:")
                msg = str(msg).replace('\n', newline)
            else:
                raise TypeError("Not all arguments converted during formatting"
                                ": msg='%s', args=%s" % (msg, args))
        return cls.log_x(lvl, msg)

    @classmethod
    def logdebug(cls, message, *args):
        r"""
        Log a DEBUG level message to the controlling terminal **only**

        :param message: Same as ``logging.debug()``
        :param \*args: Same as ``logging.debug()``
        """
        # Never split over multiple lines
        cls.log_x('debug', message, *args)

    @classmethod
    def loginfo(cls, message, *args):
        r"""
        Log a INFO level message to the controlling terminal **only**

        :param message: Same as ``logging.info()``
        :param \*args: Same as ``logging.info()``
        """
        cls.log_xn('info', message, *args)

    @classmethod
    def logwarning(cls, message, *args):
        r"""
        Log a WARNING level message to the controlling terminal **only**

        :param message: Same as ``logging.warning()``
        :param \*args: Same as ``logging.warning()``
        """
        cls.log_xn('warn', message, *args)

    @classmethod
    def logerror(cls, message, *args):
        r"""
        Log a ERROR level message to the controlling terminal **only**

        :param message: Same as ``logging.error()``
        :param \*args: Same as ``logging.error()``
        """
        cls.log_xn('error', message, *args)

    @classmethod
    def logtraceback(cls, name, exc_info, error_source, detail):
        r"""
        Log error to error, traceback to debug, of controlling terminal
        **only**
        """
        error_head = ("%s failed to %s\n%s\n%s" % (name, error_source,
                                                   detail.__class__.__name__,
                                                   detail))
        error_tb = traceback.format_exception(exc_info[0],
                                              exc_info[1],
                                              exc_info[2])

        error_tb = "".join(error_tb).strip() + "\n"
        cls.logerror(error_head)
        cls.logdebug(error_tb)
