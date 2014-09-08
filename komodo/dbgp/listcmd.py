#!/usr/bin/env python
# Copyright (c) 2003-2006 ActiveState Software Inc.
#
# The MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is furnished
# to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#
# Authors:
#    Trent Mick <TrentM@ActiveState.com>


"""An alternate version of the cmd.Cmd object for command-line handling
that uses argument vectors instead of command strings. This is much more
handy.

Also, some minor changes have been made to some default behaviours of
the cmd.Cmd class.

XXX Describe those differences here.
"""
# TODO:
# - see XXX's and TODO's below
# - port to cmd.Cmd changes in Python 2.3 (stdout and stdin ctor args)
# - add tests for the actual ListCmd class :)
# - LaTeX documentation

import os
import sys
import cmd



_version_ = (0, 1, 0)

class ListCmdError(Exception):
    pass



def line2argv(line):
    r"""Parse the given line into an argument vector.

        "line" is the line of input to parse.

    This may get niggly when dealing with quoting and escaping. The
    current state of this parsing may not be completely thorough/correct
    in this respect.

    >>> from listcmd import line2argv
    >>> line2argv("foo")
    ['foo']
    >>> line2argv("foo bar")
    ['foo', 'bar']
    >>> line2argv("foo bar ")
    ['foo', 'bar']
    >>> line2argv(" foo bar")
    ['foo', 'bar']
    >>> line2argv("'foo bar'")
    ['foo bar']
    >>> line2argv('"foo bar"')
    ['foo bar']
    >>> line2argv(r'"foo\"bar"')
    ['foo"bar']
    >>> line2argv("'foo bar' spam")
    ['foo bar', 'spam']
    >>> line2argv("'foo 'bar spam")
    ['foo bar', 'spam']
    >>> line2argv('some\tsimple\ttests')
    ['some', 'simple', 'tests']
    >>> line2argv('a "more complex" test')
    ['a', 'more complex', 'test']
    >>> line2argv('a more="complex test of " quotes')
    ['a', 'more=complex test of ', 'quotes']
    >>> line2argv('a more" complex test of " quotes')
    ['a', 'more complex test of ', 'quotes']
    >>> line2argv('an "embedded \\"quote\\""')
    ['an', 'embedded "quote"']

    # Komodo bug 48027
    >>> line2argv('foo bar C:\\')
    ['foo', 'bar', 'C:\\']

    # Komodo change 127581
    >>> line2argv(r'"\test\slash" "foo bar" "foo\"bar"')
    ['\\test\\slash', 'foo bar', 'foo"bar']

    # Komodo change 127629
    >>> if sys.platform == "win32":
    ...     line2argv(r'\foo\bar') == ['\\foo\\bar']
    ...     line2argv(r'\\foo\\bar') == ['\\\\foo\\\\bar']
    ...     line2argv('"foo') == ['foo']
    ... else:
    ...     line2argv(r'\foo\bar') == ['foobar']
    ...     line2argv(r'\\foo\\bar') == ['\\foo\\bar']
    ...     try:
    ...         line2argv('"foo')
    ...     except ValueError, ex:
    ...         "not terminated" in str(ex)
    True
    True
    True
    """
    line = line.strip()
    argv = []
    state = "default"
    arg = None  # the current argument being parsed
    i = -1
    WHITESPACE = '\t\n\x0b\x0c\r '  # don't use string.whitespace (bug 81316)
    while 1:
        i += 1
        if i >= len(line): break
        ch = line[i]

        if ch == "\\" and i+1 < len(line):
            # escaped char always added to arg, regardless of state
            if arg is None: arg = ""
            if (sys.platform == "win32"
                or state in ("double-quoted", "single-quoted")
               ) and line[i+1] not in tuple('"\''):
                arg += ch
            i += 1
            arg += line[i]
            continue

        if state == "single-quoted":
            if ch == "'":
                state = "default"
            else:
                arg += ch
        elif state == "double-quoted":
            if ch == '"':
                state = "default"
            else:
                arg += ch
        elif state == "default":
            if ch == '"':
                if arg is None: arg = ""
                state = "double-quoted"
            elif ch == "'":
                if arg is None: arg = ""
                state = "single-quoted"
            elif ch in WHITESPACE:
                if arg is not None:
                    argv.append(arg)
                arg = None
            else:
                if arg is None: arg = ""
                arg += ch
    if arg is not None:
        argv.append(arg)
    if not sys.platform == "win32" and state != "default":
        raise ValueError("command line is not terminated: unfinished %s "
                         "segment" % state)
    return argv


def argv2line(argv):
    r"""Put together the given argument vector into a command line.

        "argv" is the argument vector to process.

    >>> from listcmd import argv2line
    >>> argv2line(['foo'])
    'foo'
    >>> argv2line(['foo', 'bar'])
    'foo bar'
    >>> argv2line(['foo', 'bar baz'])
    'foo "bar baz"'
    >>> argv2line(['foo"bar'])
    'foo"bar'
    >>> print argv2line(['foo" bar'])
    'foo" bar'
    >>> print argv2line(["foo' bar"])
    "foo' bar"
    >>> argv2line(["foo'bar"])
    "foo'bar"
    """
    escapedArgs = []
    for arg in argv:
        if ' ' in arg and '"' not in arg:
            arg = '"'+arg+'"'
        elif ' ' in arg and "'" not in arg:
            arg = "'"+arg+"'"
        elif ' ' in arg:
            arg = arg.replace('"', r'\"')
            arg = '"'+arg+'"'
        escapedArgs.append(arg)
    return ' '.join(escapedArgs)



class ListCmd(cmd.Cmd):
    """Pass arglists instead of command strings to commands.

    Modify the std Cmd class to pass arg lists instead of command lines.
    This seems more appropriate for integration with sys.argv which handles
    the proper parsing of the command line arguments (particularly handling
    of quoting of args with spaces).
    """
    #TODO:
    # - See the XXX's in this class.
    # - Add an "options" argument to the constructor specifying whether
    #   the special '?' and '!' things should be used. One might want to
    #   key some of this on whether operating in a command loop or not.
    # - Look at the complete_* stuff and see if it needs to be adapted.
    # - Figure out how to deal with the onecmd vs. cmdloop differences:
    #   - return code from .default()
    #   - need for self.name and usage in error messages
    # - Document this and submit to the Python core.
    prompt = "(ListCmd) "

    def logerror(self, msg):
        #XXX document this new method
        sys.stderr.write(msg+'\n')

    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse into an argv, and
        dispatch to action methods, passing them the argv.

            "intro" is a introductory method to print when starting the
                command loop. This overrides the class "intro" attribute,
                if any.
        """
        #XXX Might be nice to add a trap for KeyboardInterrupt which
        #    defers to say, self.interrupt, for handling. This handler would
        #    do nothing by default but could offer confirm that the user
        #    wants to cancel.
        self.preloop()
        if intro is not None:
            self.intro = intro
        if self.intro:
            sys.stdout.write(str(self.intro)+"\n")
        stop = None
        while not stop:
            if self.cmdqueue:
                #XXX What is the .cmdqueue? "cmd.py" does not seem to do
                #    anything useful with it.
                line = self.cmdqueue.pop(0)
            else:
                if self.use_rawinput:
                    try:
                        line = raw_input(self.prompt)
                    except EOFError:
                        line = 'EOF'
                else:
                    sys.stdout.write(self.prompt)
                    sys.stdout.flush()
                    line = sys.stdin.readline()
                    if not len(line):
                        line = 'EOF'
                    else:
                        line = line[:-1] # chop \n
            argv = line2argv(line)
            try:
                argv = self.precmd(argv)
                stop = self.onecmd(argv)
                stop = self.postcmd(stop, argv)
            except:
                if not self.onerror():
                    raise
        self.postloop()

    def onerror(self):
        """Called if an exception is raised in any of precmd(), onecmd(),
        or postcmd(). If true is returned, the exception is deemed to have
        been dealt with.
        """
        pass

    def precmd(self, argv):
        """Hook method executed just before the command argv is
        interpreted, but after the input prompt is generated and issued.
        """
        return argv

    def postcmd(self, stop, argv):
        """Hook method executed just after a command dispatch is finished."""
        return stop

    def onecmd(self, argv):
        # Differences from Cmd:
        #   - use an argv, rather than a command string
        #   - don't specially handle the '?' redirect to 'help'
        #   - don't allow the '!' shell out
        if not argv:
            return self.emptyline()
        self.lastcmd = argv
        cmdName = argv[0]
        try:
            func = getattr(self, 'do_' + cmdName)
        except AttributeError:
            return self.default(argv)
        try:
            return func(argv)
        except TypeError, ex:
            self.logerror("%s: %s" % (cmdName, ex))
            self.logerror("try 'help %s'" % cmdName)
            if 0:   # for debugging
                print
                import traceback
                traceback.print_exception(*sys.exc_info())

    def default(self, argv):
        self.logerror("unknown syntax: '%s'" % argv2line(argv))
        #XXX Would like to return 1 here to return an error code for
        #    a single command line, however this return value is used to
        #    indicate whether a command loop should stop. TODO: separate
        #    these two: return code and whether to stop loop, consider
        #    using a Stop exception or something like that.
        #return 1

    def _do_one_help(self, arg):
        try:
            # If help_<arg1>() exists, then call it.
            func = getattr(self, 'help_' + arg)
        except AttributeError:
            try:
                doc = getattr(self, 'do_' + arg).__doc__
            except AttributeError:
                doc = None
            if doc: # *do* have help, print that
                sys.stdout.write(doc + '\n')
                sys.stdout.flush()
            else:
                self.logerror("no help for '%s'" % (arg,))
        else:
            return func()

    # Technically this improved do_help() does not fit into _ListCmd, and
    # something like this would be more appropriate:
    #    def do_help(self, argv):
    #        cmd.Cmd.do_help(self, ' '.join(argv[1:]))
    # but I don't want to make another class for it.
    def do_help(self, argv):
        if argv[1:]:
            for arg in argv[1:]:
                retval = self._do_one_help(arg)
                if retval:
                    return retval
        else:
            doc = self.__class__.__doc__  # try class docstring
            if doc:
                sys.stdout.write(doc + '\n')
                sys.stdout.flush()
            elif __doc__:  # else try module docstring
                sys.stdout.write(__doc__)
                sys.stdout.flush()

    def emptyline(self):
        # Different from Cmd: don't repeat the last command for an emptyline.
        pass



#---- self-test

def _test():
    import doctest
    doctest.testmod()


if __name__ == "__main__":
    _test()


