Feature: Evaluating expressions
    In order to evaluate variables in Vdebug
    As a user
    I want to see the evaluated variable in the watch window

    Scenario: Evaluating a PHP expression
        Given I have a file example.php containing
            """
            <?php
            $var1 = 1;
            ?>
            """
        And I start the debugger with the PHP script example.php
        When I evaluate "$var1"
        Then the watch window should show Eval of: '$var1'

    Scenario: Evaluating a PHP expression with VdebugEval!
        Given I have a file example.php containing
            """
            <?php
            $var1 = 1;

            ?>
            """
        And I start the debugger with the PHP script example.php
        When I evaluate "$var1" with VdebugEval!
        Then the watch window should show Eval of: '$var1'
        When I step over
        Then the watch window should show Eval of: '$var1'

    Scenario: Evaluating a PHP expression and resetting
        Given I have a file example.php containing
            """
            <?php
            $var1 = 1;

            ?>
            """
        And I start the debugger with the PHP script example.php
        When I evaluate "$var1" with VdebugEval!
        Then the watch window should show Eval of: '$var1'
        When I run VdebugEval without any arguments
        Then the watch window should show Locals
