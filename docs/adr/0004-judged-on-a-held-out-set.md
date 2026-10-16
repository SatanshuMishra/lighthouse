# lighthouse is judged on a held-out set it is never tuned on

Six fixture projects of different kinds, each with two merged changes whose combination hides an integration bug from the project's own suite, decide whether lighthouse works: every bug named on both runs, every clean twin green, no broken fixture ever green. The Steps that write the skills never see the fixtures, and a leak test keeps fixture identifiers out of skills and code, so passing the set says something about projects nobody has seen.
