# AI Usage Disclosure

## Tools used
Claude (chat), and I ran everything in VS Code.

## What I used them for
- Explained the assignment and the terms in simple language
- Helped design the approach (tables, hashing for phone numbers, calculating reports at report time)
- Wrote the first drafts of the code and tests, and the drafts of the documents
- Helped me fix setup and test errors (virtual environment, pytest config, missing files)

## What I wrote or decided myself
- I choose the Assignment 1 beacuse the answer are easier to check
- I set up the VScode, the virtual environment and git myself and fixed the errors I hit
- I checked the report numbers by hand: the rejection reasons add up to 108, and events add up to 8745 (4247 + 4498) 
- I decided what to list as “not handled” in SUBMISSION.md.

## Where the AI was wrong or unhelpful
- My pytest.ini gave an error ‘unexpected value continuation’ after pasting, so I had to retype it by hand.
- After a step, pytest ran 25 tests, not 26. I noticed test_pipeline.py was missing, and added it.
- Pytest said No module named ledger.events because a file from an earlier step was missing. I created it.


## How I verified AI-generated code
- Ran the tests (26 pass), including an idempotency test on a seed I had not developed on
- Checked the totals in the reports against each other by hand
- I'm going through each file line by line so I can explain it, starting with reports.py