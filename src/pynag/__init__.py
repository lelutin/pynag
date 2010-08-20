# -*- coding: utf-8 -*-
#############################################################################
#                                                                           #
#    Nagios custom plugins -- A python library and a set of Nagios plugins. #
#    Copyright (C) 2010  Revolution Linux, inc. <info@revolutionlinux.com>  #
#                                                                           #
#    This program is free software: you can redistribute it and/or modify   #
#    it under the terms of the GNU General Public License as published by   #
#    the Free Software Foundation, either version 3 of the License, or      #
#    (at your option) any later version.                                    #
#                                                                           #
#    This program is distributed in the hope that it will be useful,        #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of         #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          #
#    GNU General Public License for more details.                           #
#                                                                           #
#    You should have received a copy of the GNU General Public License      #
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.  #
#                                                                           #
#############################################################################
import sys
import os
import time
import signal
from optparse import OptionParser


# Standard return codes for Nagios plugins
RETURN_CODES = {
    "OK": 0,
    "WARNING": 1,
    "CRITICAL": 2,
    "UNKNOWN": 3,
    "DEPENDANT": 4
}

# Debugging output can be enabled programatically by setting this value to
# True, but the easiest and most flexible way of enabling debugging is by
# setting the NAGIOS_DEBUG environment variable to a non-false value.
DEBUG = os.getenv("NAGIOS_DEBUG") or False

# This value could be changed by the plugin to "hijack" the output. The only
# correct use for this is probably for testing/debugging, though.
output_stream = sys.stdout

def nagios_debug(message, *args):
    """Print a debugging message if enabled.

    The message is only output if DEBUG is set to True. Use this function in
    your check to specify your check's debugging output.

    """
    if DEBUG:
        print >> output_stream, "DEBUG: %s" % (message % args)


class NullStream(object):
    """Trash stream that does nothing with output."""
    def writelines(self, text):
        pass
    def write(self, text):
        pass


class TimeoutException(Exception):
    """Exception raised on a timeout"""
    pass


class TimeoutFunction(object):
    """Stop execution of a function after defined time if it is not complete.

    Wrap around a function and determine a timeout in number of seconds. A
    TimeoutException is raised if the function did not complete after the time
    has been elapsed. A timeout value of 0 disables the timeout.

    WARNING: This class uses the alarm signal. Only one alarm can be set at a
    time. Thus, if an alarm is set during execution the wrapped function, the
    timeout will be overridden and execution of the wrapped function will never
    be stopped by the timeout.

    """
    def __init__(self, function, timeout):
        assert(timeout >= 0)
        self.timeout = timeout
        self.function = function

    def _handle_timeout(self, signum, frame):
        raise TimeoutException()

    def __call__(self, *args, **kwargs):
        if not self.timeout:
            # Timeout disabled
            return self.function(*args, **kwargs)

        old = signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.alarm(self.timeout)
        try:
            result = self.function(*args, **kwargs)
        finally:
            signal.signal(signal.SIGALRM, old)
        signal.alarm(0)
        return result


class ExecutionCritical(Exception):
    pass

class ExecutionWarning(Exception):
    pass

class ExecutionUnknown(Exception):
    pass

class ExecutionDependant(Exception):
    pass


class Check(object):
    """A check that will be executed as a Nagios plugin.

    The constructor receives a function and optionally a success message and a
    timeout integer value (seconds before execution stops). Passing a success
    message that suits your check is strongly advised. If the timeout is
    reached, the check is considered a critical failure. The default timeout is
    10 seconds.

    The Check class also parses arguments from the command line. You can add
    options for your check by calling add_option(). The options will be parsed
    just before execution of the check. Two arguments are then passed to the
    check representing the options and the positional arguments, respectively.
    The check function should hence be able to receive those to values as
    arguments.

    The check function's returned value will be used as the success check
    status. To signify another status to Nagios, the check function should
    raise the appropriate exception. A short message corresponding to the state
    should be passed on to the exception's constructor:

        ExecutionWarning   -- Indicates a warning. Returns code 1
        ExecutionCritical  -- Indicates a critical failure. Returns code 2
        ExecutionUnknown   -- The state of the check is unkown. Returns code 3
        ExecutionDependant -- A dependancy is in unknown state. Returns code 4

    A hook function can be called before exit when a timeout is reached. This
    makes it possible to do cleanup work before failing.

    A default verbose command-line option is created. Both the check and the
    cleanup functions can output verbose information by simply printing text to
    standard out. This output is visible only when -v or --verbose is given on
    the command-line.

    """
    def __init__(self, func, name, extended_usage_text=None, timeout=10,
                 cleanup_timeout=60):
        msg = ''.join(["Check initialization arguments: name=\"%s\", ",
                       "timeout %d, cleanup_timeout=%d."])
        nagios_debug(msg, name, timeout, cleanup_timeout)
        self.check = func
        self.name = name

        self.options = OptionParser()
        self.options.add_option("-v", "--verbose",
            dest="verbose", action="store_true", default=False,
            help="Let the check output more information on what is happening")
        self.options.add_option( "--timeout",
            dest="timeout", type="int", default=timeout,
            help="Number of seconds before the check times out. 0 disables the "
                 "timeout (default: %d)" % timeout )
        self.options.add_option( "--cleanup-timeout",
            dest="cleanup_timeout", type="int", default=cleanup_timeout,
            help="Number of seconds before the cleanup function times out "
                 "(default: %d seconds)" % cleanup_timeout )

        self.extended_usage(extended_usage_text)

        self.old_stdout = sys.stdout
        self.cleanup_callback = None
        # This value should not be used. It is just set to ensure that calling
        # _exit before run doesn't create an explosion.
        self.cleanup_timeout = 60

    def _exit(self, type, message):
        """Print a message and exit with the appropriate code.

        This is the Nagios-compliant exit mechanism. Exiting with this code
        should only be called by the main (controller) thread.

        """
        time_elapsed = (time.time() - self.start_time)
        nagios_debug("Time elapsed during check: %s", time_elapsed)

        if self.cleanup_callback:
            nagios_debug("Invoking cleanup callback \"%s\".", self.cleanup_callback.function.__name__)
            try:
                cleanup_func = TimeoutFunction(self.cleanup_callback, self.cleanup_timeout)
                cleanup_func(type)
            except TimeoutException:
                pass
        else:
            nagios_debug("No cleanup callback defined, skipping.")

        # Restore original stdout object
        sys.stdout = self.old_stdout

        print "%s %s: %s" % (self.name, type, message)
        sys.exit(RETURN_CODES[type])

    def critical(self, message):
        """Nagios-compliant critical failure."""
        self._exit("CRITICAL", message)

    def warning(self, message):
        """Nagios-compliant warning failure."""
        self._exit("WARNING", message)

    def success(self, message):
        """Nagios-compliant execution success."""
        self._exit("OK", message)

    def unknown(self, message):
        """Nagios-compliant exit with unknown state."""
        self._exit("UNKNOWN", message)

    def dependant(self, message):
        """Nagios-compliant exit with dependant state."""
        self._exit("DEPENDANT", message)

    def set_cleanup(self, cleanup=None):
        """Set the pre-exit callback.

        The callback will be invoked just before the check exits and outputs
        its status.

        To unregister a callback, give None to the 'cleanup' argument.

        The callback will be invoked with one argument only. The argument is a
        string corresponding to the type of exit that happened and can be used
        to determined what needs to be done.

        """
        if cleanup is not None and not callable(cleanup):
            raise TypeError("Cleanup callback argument must be a callable object")

        nagios_debug("Registered callback function named \"%s\" at \"%s\".", cleanup.__name__, cleanup)
        self.cleanup_callback = cleanup

    def add_option(self, *args, **kwargs):
        """Add an option that should be parsed from command line.

        All the arguments of this method will be passed on to optparse.Option's
        constructor. The options will be parsed just before execution of the
        check.

        """
        nagios_debug("Added new option \"%s\" to the parser.", kwargs.get("dest", "") )
        self.options.add_option(*args, **kwargs)

    def extended_usage(self, help_text=None):
        """Set the usage text for positional arguments.

        'help_text' will be appended to the default usage string. This is
        useful if your check uses positional arguments since optparse doesn't
        generate this automatically.

        Call this function with no argument to remove the extra usage text.

        """
        default_usage = "%prog [options]"

        if help_text:
            self.options.usage = "%s %s" % (default_usage, help_text)
        else:
            self.options.usage = default_usage

    def run(self):
        """Run the check.

        Exit with a given code and message formatted according to Nagios plugin
        rules. To trigger an exit state from within the check, simply raise an
        Execution* exception.

        If the check takes too much time, as defined by the timeout given to
        the constructor, execution of the check will be halted and the check
        will exit with a critical status.

        Text output during execution of both the check and the cleanup
        functions is considered "verbose" output. It will be sent to standard
        out only if the option "-v" (or "--verbose") is given on the command
        line.

        """
        (options, args) = self.options.parse_args()

        self.cleanup_timeout = options.cleanup_timeout

        self.start_time = time.time()

        try:
            if not options.verbose:
                # Divert the standard output stream to hide verbose output
                self.old_stdout = sys.stdout
                sys.stdout = NullStream()

            check_func = TimeoutFunction(self.check, options.timeout)
            success_message = check_func(options, args)
        except TimeoutException:
            nagios_debug("Timeout reached.")
            values = (options.timeout, (options.timeout > 1) and "s" or "")
            self.unknown("Timeout reached (%f second%s)" % values )
        # The following are execution statuses signified by the check function
        except ExecutionCritical:
            (d1, message, d2) = sys.exc_info()
            self.critical(message)
        except ExecutionWarning:
            (d1, message, d2) = sys.exc_info()
            self.warning(message)
        except ExecutionUnknown:
            (d1, message, d2) = sys.exc_info()
            self.unknown(message)
        except ExecutionDependant:
            (d1, message, d2) = sys.exc_info()
            self.dependant(message)
        # Nothing was raised, success
        else:
            self.success(success_message)

        # This code should never be reached.. but you never know!
        sys.stdout = self.old_stdout
