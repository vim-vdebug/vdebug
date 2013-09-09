Feature: Correct window setup
    In order to use Vdebug with all window panels
    As a user
    I want to see correct watch, stack and status information

    Scenario: The watch window
        Given I have a file example.php containing
            """
            <?php
            $var1 = 1;
            $var2 = array("hello", "world");
            ?>
            """
        And I start the debugger with the PHP script example.php
        When I step over
        Then the watch window should show the variable $var1
        And the watch window should show the variable $var2
        And the watch window variable $var1 should be (int) 1
        And the watch window variable $var2 should be (uninitialized)

    Scenario: The stack window
        Given I have a file example.php containing
            """
            <?php
            $var1 = 1;
            $var2 = array("hello", "world");
            ?>
            """
        And I start the debugger with the PHP script example.php
        When I step over
        Then the first item on the stack should show the file example.php
        And the first item on the stack should show line 3
