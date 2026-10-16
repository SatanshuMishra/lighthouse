# greenhand

greenhand is a Claude Code plugin that helps people look after houseplants. Each skill handles one kind of request, and its description decides which requests start it.

## Skills

- `houseplant-care`: how to water, feed or repot a specific houseplant.
- `seed-sowing`: when and how to sow seeds indoors.

## Use

Load the plugin into a Claude Code session from the repository root:

    claude --plugin-dir .

Then ask a plant question in plain words, for example "How often should I water a snake plant?". Each skill opens its reply with its own heading line, so the reply shows which skill answered.

## Tests

The tests check the plugin manifest and every skill's SKILL.md frontmatter. Run them from the repository root with:

    python3 -m unittest discover -s tests
