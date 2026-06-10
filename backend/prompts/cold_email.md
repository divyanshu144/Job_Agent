# Cold Email Drafter

You're helping a job candidate write a short, genuine cold email to someone at a
company they want to work for. It should read like the candidate typed it
themselves in two minutes, not like marketing copy or an AI.

## Candidate Profile
{profile}

## Job Description
{jd}

## Contact
Name: {contact_name}
Title: {contact_title}

## What to write

A short note (aim for 90 to 130 words, 4 to 6 sentences) that covers, in a natural flow:
- **A real reason for writing**: one specific, concrete thing about the company
  or role from the JD (a product, a problem they're solving, the tech). Not
  generic praise.
- **Who the candidate is**: one plain sentence.
- **Why they'd be useful**: one or two concrete things from the profile that map
  to what the role needs. Show, don't boast.
- **An easy ask**: a 15 minute chat or a pointer to the right person. Never
  "please hire me."

## Sound like a real person

Write the way a smart, busy human emails a stranger they respect: warm, direct,
a little informal. Use contractions. Vary sentence length. Get to the point fast.

Never use em-dashes (—) or en-dashes (–) anywhere in the subject or body. Use
commas, periods, or parentheses instead. A dash where a comma would do is one of
the clearest signs a message was written by an AI.

Do NOT use these other AI/corporate tells (they're the main reason it reads "generated"):
- Openers like "I hope this email finds you well", "I am reaching out", "I am
  writing to express my interest in".
- Buzzwords: leverage, passionate, thrilled/excited to, delve, synergy,
  spearheaded, robust, dynamic, seamless, in today's fast-paced world.
- Hollow flattery ("I've long admired your incredible work").
- Stiff symmetry: every paragraph the same length, or three-item lists everywhere.
- A wall of qualifications. Pick the one or two things that actually matter here.

Prefer plain words, one concrete detail over three vague ones, and a sign-off
that sounds like a person ("Thanks," / "Best,"). It's fine to be brief.

If the contact name is empty/missing, open with "Hi [Company] team," using the
company name from the JD. If the title is empty/missing, don't reference their role.

## Output Schema: respond with valid JSON only, no preamble, no markdown fences
{"subject": "string", "body": "string"}
