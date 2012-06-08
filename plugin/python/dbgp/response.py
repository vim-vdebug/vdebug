import xml.etree.ElementTree as ET

""" Response objects for the DBGP module."""

class Response:
    """Contains response data from a command made to the debugger."""

    def __init__(self,response,cmd,cmd_args):
        self.response = response
        self.cmd = cmd
        self.cmd_args = cmd_args
        self.xml = None
        if "<error" in self.response:
            self.__parse_error()

    def __parse_error(self):
        """Parse an error message which has been returned
        in the response, then raise it as a DBGPError."""
        xml = self.as_xml()
        err_el = xml.find('error')
        code = err_el.get("code")
        if code is None:
            raise ResponseError(
                    "Missing error code in response",
                    self.response)
        msg_el = err_el.find('message')
        if msg_el is None:
            raise ResponseError(
                    "Missing error message in response",
                    self.response)
        raise DBGPError(msg_el.text,code)

    def get_cmd(self):
        """Get the command that created this response."""
        return self.cmd

    def get_cmd_args(self):
        """Get the arguments to the command."""
        return self.cmd_args

    def as_string(self):
        """Return the full response as a string.
        
        There is a __str__ method, which will render the
        whole object as a string and should be used for
        displaying.
        """
        return self.response

    def as_xml(self):
        """Get the response as element tree XML.

        Returns an xml.etree.ElementTree.Element object.
        """
        if self.xml == None:
            self.xml = ET.fromstring(self.response)
        return self.xml

    def __str__(self):
        return self.as_string()

class StatusResponse(Response):
    """Response object returned by the status command."""

    def __str__(self):
        return self.as_xml().get('status')

class FeatureGetResponse(Response):
    """Response object specifically for the feature_get command."""

    def is_supported(self):
        """Whether the feature is supported or not."""
        xml = self.as_xml()
        return int(xml.get('supported'))

    def __str__(self):
        if self.is_supported():
            xml = self.as_xml()
            return xml.text
        else:
            return "* Feature not supported *"
""" Errors/Exceptions """

class DBGPError(Exception):
    """Raised when the debugger returns an error message."""
    pass

class ResponseError(Exception):
    """An error caused by an unexpected response from the
    debugger (e.g. invalid format XML)."""
    pass

error_codes = { \
    # 000 Command parsing errors
    0   : """no error""",\
    1   : """parse error in command""",\
    2   : """duplicate arguments in command""", \
    3   : """invalid options (ie, missing a required option)""",\
    4   : """Unimplemented command""",\
    5   : """Command not available (Is used for async commands. For instance if the engine is in state "run" than only "break" and "status" are available). """,\
    # 100 : File related errors
    100 : """can not open file (as a reply to a "source" command if the requested source file can't be opened)""",\
    101 : """stream redirect failed """,\
    # 200 Breakpoint, or code flow errors
    200 : """breakpoint could not be set (for some reason the breakpoint could not be set due to problems registering it)""",\
    201 : """breakpoint type not supported (for example I don't support 'watch' yet and thus return this error)""",\
    202 : """invalid breakpoint (the IDE tried to set a breakpoint on a line that does not exist in the file (ie "line 0" or lines past the end of the file)""",\
    203 : """no code on breakpoint line (the IDE tried to set a breakpoint on a line which does not have any executable code. The debugger engine is NOT required to """     + \
          """return this type if it is impossible to determine if there is code on a given location. (For example, in the PHP debugger backend this will only be """         + \
          """returned in some special cases where the current scope falls into the scope of the breakpoint to be set)).""",\
    204 : """Invalid breakpoint state (using an unsupported breakpoint state was attempted)""",\
    205 : """No such breakpoint (used in breakpoint_get etc. to show that there is no breakpoint with the given ID)""",\
    206 : """Error evaluating code (use from eval() (or perhaps property_get for a full name get))""",\
    207 : """Invalid expression (the expression used for a non-eval() was invalid) """,\
    # 300 Data errors
    300 : """Can not get property (when the requested property to get did not exist, this is NOT used for an existing but uninitialized property, which just gets the """    + \
          """type "uninitialised" (See: PreferredTypeNames)).""",\
    301 : """Stack depth invalid (the -d stack depth parameter did not exist (ie, there were less stack elements than the number requested) or the parameter was < 0)""",\
    302 : """Context invalid (an non existing context was requested) """,\
    # 900 Protocol errors
    900 : """Encoding not supported""",\
    998 : """An internal exception in the debugger occurred""",\
    999 : """Unknown error """\
}
