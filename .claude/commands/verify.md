# Verify

Run the strongest practical verification for the current repository.

Check:
- git diff
- typecheck
- lint
- tests
- production build
- obvious runtime errors

For UI changes also inspect:
- mobile
- desktop
- keyboard
- reduced motion
- empty/loading/error states

Do not modify unrelated code.

If something fails:
1. diagnose root cause
2. fix it
3. rerun the failed check
