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
import time
import signal
from optparse import OptionParser, Option

# Standard return codes for Nagios plugins
RETURN_CODES = {
    "OK": 0,
    "WARNING": 1,
    "CRITICAL": 2,
    "UNKNOWN": 3,
    "DEPENDANT": 4
}

# To enable debugging output for your test, set this value to True before
# instantiating the Check object in the following manner:
#
# import nagios
# nagios.DEBUG = True
DEBUG = False

# This value could be changed by the plugin to "hijack" the output. The only
# correct use for this is probably for testing/debugging, though.
output_stream = sys.stdout

# Use this function in your check to specify your check's debugging output.
def nagios_debug(message):
    """Print some message identified as debug output.

    The message is only output if DEBUG is set to True. Use this function in
    your check to specify your check's debugging output.

    """
    if DEBUG:
        print >> output_stream, "DEBUG: %s" % message

class NullStream(object):
    """Trash stream. Do nothing with output."""
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
    has been elapsed.

    WARNING: This class uses the alarm signal. Python only keeps one alarm at a
    time. Thus, if an alarm is set during execution of either the wrapped
    function or the try/except block surrounding the call, the timeout will be
    overridden and thus, execution of the wrapped function will never be
    stopped by the timeout.

    """
    def __init__(self, function, timeout):
        self.timeout = timeout
        self.function = function

    def _handle_timeout(self, signum, frame):
        raise TimeoutException()

    def __call__(self, *args, **kwargs):
        old = signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.alarm(self.timeout)
        try:
            result = self.function(*args, **kwargs)
        finally:
            signal.signal(signal.SIGALRM, old)
        signal.alarm(0)
        return result

class ExecutionCritical(Exception):
    """This exception should be raised by a check function to signify a problem"""
    pass

class ExecutionWarning(Exception):
    """This exception should be raised by a check function to signify a warning"""
    pass

class ExecutionUnknown(Exception):
    """This exception should be raised if the test result is unkown"""
    pass

class ExecutionDependant(Exception):
    """This exception should be raised if the test depends on something"""
    pass

class Check(object):
    """This is a check that will be executed as a Nagios plugin.

    This class defines a check that should be executed by Nagios. The
    constructor receives a function and optionally a success message and a
    timeout value. Passing a success message that suits your check is strongly
    advised. The timeout value is an integer representing the time in seconds
    allowed for the check to complete. If this much time is elapsed before the
    check completes, the check is considered a critical failure. The default
    timeout is 30 seconds.

    The Check class also parses arguments from the command line. You can add
    options for your check by giving an instance of Option from optparse to
    this class' add_option method. The options will be parsed just before
    execution of the check. Two arguments are then passed to the check
    representing, respectively, the options and the positional arguments. The
    check function should hence be able to receive those to values as
    arguments.

    If the check function exits without raising any exception, it is considered
    to be a success. To signify another status to Nagios, the check function
    should raise the appropriate exception. A short message corresponding to
    the state should be passed on to the exception's constructor:

        ExecutionCritical -- Indicates a critical failure.
        ExecutionWarning -- Indicates a warning.
        ExecutionUnknown -- The state of the check is unkown.

    A function can be hooked right before exiting on a timeout. This makes it
    possible to do cleanup work to free resources.

    A default verbose option is created. Both the check and the cleanup
    functions can output verbose information by simply printing text to
    standard out. This output will not be visible by default.

    """
    def __init__(self,
            func, name, extended_usage_text=None,
            timeout=30, cleanup_timeout=60):
        """Constructor for Check.

        Arguments:
            func -- A function (the check) that must take in two arguments.
            name -- small identifier usually in caps prepended to the output.
            succ_message -- A string printed upon check success.

        """
        msg = """Check initialization arguments: name="%s", """ + \
              """timeout %d, cleanup_timeout=%d."""
        nagios_debug(
             msg % (name, timeout, cleanup_timeout)
        )
        self.check = func
        self.name = name

        self.options = OptionParser()
        self.options.add_option("-v", "--verbose",
            dest="verbose", action="store_true", default=False,
            help="Let the check output more information on what is happening")
        self.options.add_option( "--timeout",
            dest="timeout", type="int", default=timeout,
            help="Number of seconds before the check times out "
                 "(default: %d)" % timeout )
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
        """Exit by printing a message and returning the appropriate value.

        This is the Nagios-compliant exit mechanism. Exiting with this code
        should only be called by the main (controller) thread.

        """
        time_elapsed = (time.time() - self.start_time)
        nagios_debug("Time elapsed during check: %s" % time_elapsed)

        if self.cleanup_callback:
            nagios_debug("""Invoking cleanup callback "%s".""" % self.cleanup_callback.function.__name__)
            try:
                cleanup_func = TimeoutFunction(self.cleanup_callback, self.cleanup_timeout)
                cleanup_func(type)
            except TimeoutException:
                pass
        else:
            nagios_debug("""No cleanup callback defined, skipping.""")

        #Restore original stdout value
        sys.stdout = self.old_stdout

        print "%s %s: %s" % (self.name, type, message)
        nagios_debug("Check returned with exit code %d" % RETURN_CODES[type])
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
        """Set the callback to execute before exiting.

        This registers a callable object to be called upon termination of a check.
        The callback will be invoked just before the check exits and outputs
        its status. A cleanup callback should usually be used to close files,
        release locks and other resources before abandoning work.

        To unregister a callback, call this function with no argument.

        The callback will be invoked with one argument only. The argument is a
        string corresponding to the type exit that happened and can be used to
        determined what needs to be done.

        """
        import collections
        if cleanup is not None and not callable(cleanup):
            raise TypeError("Cleanup callback argument must be a callable object")

        nagios_debug("""Registered callback function named "%s" at "%s".""" % (cleanup.__name__, cleanup) )
        self.cleanup_callback = cleanup

    def add_option(self, new_option):
        """Add an option that should be parsed from command line.

        This adds an option to the option parser. The "new_option" argument
        should be an instance of Option from the optparse library. The options
        will be parsed just before execution of the check given to the Check
        constructor.

        """
        if not isinstance(new_option, Option):
            raise TypeError("Argument is not an optparse.Option instance")

        nagios_debug("""Added new option "%s" to the parser.""" % new_option.dest)
        self.options.add_option(new_option)

    def extended_usage(self, help_text=None):
        """Set the usage text for positional arguments.

        Define a string to append to the usage string. This is useful if your
        check uses positional arguments as optparse doesn't generate this
        automatically.

        This function could also be used to set a concise description of your
        plugin on lines just below usage. Remember this text will also be
        present when the check exits because an invalid argument was passed via
        the command line.

        Call this function with no argument to remove the extra usage text.

        """
        default_usage = "%prog [options]"

        if help_text:
            self.options.usage = "%s %s" % (default_usage, help_text)
        else:
            self.options.usage = default_usage

    def run(self):
        """Run the check.

        This method runs the check. It will exit with a given code and message
        formatted according to Nagios plugin rules. To trigger an exit state
        from within the check, simply raise an Execution* exception.

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
                # Divert the standard output stream to block verbose output
                self.old_stdout = sys.stdout
                sys.stdout = NullStream()

            check_func = TimeoutFunction(self.check, options.timeout)
            success_message = check_func(options, args)
        except TimeoutException:
            nagios_debug("""Timeout reached.""")
            self.critical("Timeout reached (%f second%s)" % (options.timeout, (options.timeout > 1) and "s" or "") )
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

