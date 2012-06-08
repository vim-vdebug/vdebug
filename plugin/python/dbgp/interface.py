import dbgp.response
import xml.etree.ElementTree as ET

class Interface:
    """Interface for DBGP commands.

    Uses a Connection object to read and write with the debugger,
    and builds commands and returns the results.
    """

    conn = None
    transID = 0

    def __init__(self,connection,exp_idekey = None):
        """Create a new Interface using a Connection object.

        The Connection object specifies the debugger connection,
        and the Protocol provides a OO interface to interacting
        with it.

        connection -- The Connection object to use
        """
        self.language = None
        self.protocol = None
        self.exp_idekey = exp_idekey
        self.idekey = None
        self.conn = connection
        if self.conn.isconnected() == 0:
            self.conn.open()
        self.__parse_init_msg(self.conn.recv_msg())
        
    def __parse_init_msg(self,msg):
        """Parse the init message from the debugger"""
        xml = ET.fromstring(msg)
        self.language = xml.get("language")
        if self.language is None:
            raise dbgp.response.ResponseError(
                "Invalid XML response from debugger",
                msg)

        self.idekey = xml.get("idekey")
        if self.exp_idekey is not None:
            if self.idekey != self.exp_idekey:
                raise WrongIDEKeyException()
        self.version = xml.get("interface_version")

    def send_cmd(self,cmd,args = '',
            res_cls = dbgp.response.Response):
        """Send a command to the debugger.

        This method automatically adds a unique transaction
        ID to the command which is required by the debugger.

        Returns a Response object, which contains the
        response message and command.

        cmd -- the command name, e.g. 'status'
        args -- arguments for the command, which is optional 
                for certain commands (default '')
        """
        args = args.strip()
        send = cmd.strip()
        self.transID += 1
        send += ' -i '+ str(self.transID)
        if len(args) > 0:
            send += ' ' + args
        self.conn.send_msg(send)
        msg = self.conn.recv_msg()
        return res_cls(msg,cmd,args)

    def status(self):
        """Get the debugger status.
        
        Returns a Response object.
        """
        return self.send_cmd('status','',dbgp.response.StatusResponse)

    def feature_get(self,name):
        """Get the value of a feature from the debugger.

        See the DBGP documentation for a list of features.
        
        Returns a FeatureGetResponse object.
        
        name -- name of the feature, e.g. encoding
        """
        return self.send_cmd(
                'feature_get',
                '-n '+str(name),
                dbgp.response.FeatureGetResponse)

    def feature_set(self,name,value):
        """Set the value of a debugger feature.

        See the DBGP documentation for a list of features.
        
        Returns a Response object.
        
        name -- name of the feature, e.g. encoding
        value -- new value for the feature
        """
        return self.send_cmd(
                'feature_set',
                '-n ' + str(name) + ' -v ' + str(value))

    def run(self):
        """Tell the debugger to start or resume
        execution."""
        return self.send_cmd('run','',dbgp.response.StatusResponse)

    def step_into(self):
        """Tell the debugger to step to the next
        statement.
        
        If there's a function call, the debugger engine
        will break on the first statement in the function.
        """
        return self.send_cmd('step_into','',dbgp.response.StatusResponse)

    def step_over(self):
        """Tell the debugger to step to the next
        statement.
        
        If there's a function call, the debugger engine
        will stop at the next statement after the function call.
        """
        return self.send_cmd('step_over','',dbgp.response.StatusResponse)

    def step_out(self):
        """Tell the debugger to step out of the statement.
        
        The debugger will step out of the current scope.
        """
        return self.send_cmd('step_out','',dbgp.response.StatusResponse)

    def stop(self):
        """Tell the debugger to stop execution.

        The script is terminated immediately."""
        return self.send_cmd('stop','',dbgp.response.StatusResponse)

    def detach(self):
        """Tell the debugger to detach itself from this
        client.

        The script is not terminated, but runs as normal
        from this point."""
        return self.send_cmd('detach','',dbgp.response.StatusResponse)


class WrongIDEKeyException(Exception):
    """An exception raised when the debugger session key is
    different to the expected one."""
    pass
