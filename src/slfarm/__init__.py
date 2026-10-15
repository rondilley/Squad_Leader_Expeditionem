"""The game farm: remote hosts that play the games of a gauntlet or an evolution.

`slfarm.server` runs on each host and plays the games it gets in a pool of its own.
`slfarm.client` sends the games of one job list to the hosts and to the local workers, and
gives the results back in the order of the list, so a run with the farm gives the same
artifact as a run on one machine (TR-02). `slfarm.protocol` holds the messages, the key,
the code hash, and the checks of a job.
"""
