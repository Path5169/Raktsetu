# RaktSetu: live blood network (Phase 1: engine + CLI)
Python 3.8+, standard library only.

    python -m raktsetu init                 # create DB + demo data (Nagpur, fictional)
    python -m raktsetu stock                # stock by group per bank (-c PLT for platelets)
    python -m raktsetu expiring --days 3    # FEFO expiry list
    python -m raktsetu compat A+            # who can give to / receive from
    python -m raktsetu add orange B- 2      # add units (audited)
    python -m raktsetu audit
    python -m unittest discover tests -v    # run tests

## Web UI
    python -m raktsetu serve        # opens http://127.0.0.1:8000

## Emergency engine
    python -m raktsetu request "city" B- 1      # rank banks, reserve the best (30 min hold)
    python -m raktsetu request unverified A+    # blocked: hospital not verified
    python -m raktsetu race B- -n 20            # 20 simultaneous requests, shows 0 oversold
