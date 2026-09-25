"""Приём голоса: окно, дедуп cookie, шард счётчика, журнал.

Порядок на POST: публикация, окно, вариант, SET NX, HINCRBY, запись в vote.
При VOTE_ASYNC строка журнала уходит из запроса зрителя в пачку.
"""

JOURNAL_BATCH_SIZE = 1000
JOURNAL_FLUSH_INTERVAL_SECONDS = 0.05
