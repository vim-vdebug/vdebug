Feature: Tracing expressions
    In order to trace variables in Vdebug
    As a user
    I want to see the evaluated expression in the trace window

    Scenario: Tracing a PHP expression
        Given I have a file example.php containing
            """
            <?php
            $var1 = 1;
            $var2 = 3;
            ?>
            """
        And I start the debugger with the PHP script example.php
        When I trace "$var1"
        And I step over
        Then the trace window should show Trace of: '$var1'
        And the trace window should show $var1 = (int) 1
        When I step over
        Then the trace window should show Trace of: '$var1'
        And the trace window should show $var1 = (int) 1
