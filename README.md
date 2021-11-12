# epm

Command-line TV episode calendar/manager/scheduler/tracker (EPisode Manager)

## Dependencies

- requests [https://pypi.org/project/requests]


## Examples

Add a series you'd like to monitor.

    > epm .add twin peaks 
    Found 10 series:
       #1 Twin Peaks                             1990-1991
       #2 Twin Peaks                             2017-    
       #3 Twin                                   2019-    
       #4 Georgia Coffee: Twin Peaks             1993-    
       #5 Twin Turbos                            2018-2020
       #6 Twin Hawks                             1984-1985
       #7 Twin of Brothers                       2004-    
       #8 Lexi & Lottie: Trusty Twin Detectives  2016-2017
       #9 Twin Hearts                            2003-2004
      #10 Twin My Heart                          2019-    
    Select series (1 - 10) to add --> 1    [user input]
    Series added:  (series renumbered)
       #1 Twin Peaks  1990-1991  tt0098936

Now the series is added.

All added series can be listed by using the `list` / `ls` command:

    > epm .ls
       #1 Twin Peaks              1990-1991  tt0098936
           Total: Unseen: 30  1d 53min
           Next: s1e01 Pilot  

Mark episodes that has been watched:

    > epm .mark 1 s1
    Marked 8 episodes as seen:  7h
       [edit]list of episodes cut out[/edit]
	> epm .mark 1 s2e1-20
    Marked 20 episodes as seen:  16h 17min
       [edit]list of episodes cut out[/edit]

Then, show current status, using no arguments (or the `unseen` command):

    > epm
       #1 Twin Peaks             1990-1991   1 episode
        Next: s2e21 Episode #2.21              
