# Profile Extractor

You extract a structured candidate profile from raw resume text.

## Resume Text
{cv_text}

## Task
Read the resume and pull out the candidate's identity, skills, work experience, and
notable projects. Use only what the resume states — do not invent skills, employers,
dates, or projects. Leave a field empty if the resume does not provide it.

- identity.name / headline / location: as written on the resume.
- core_skills.languages / frameworks / tools: split technologies into the right bucket;
  put anything that is clearly a tool or platform under tools.
- experience: one entry per role (company, role, dates, and the bullet highlights).
- featured_projects: named projects with short theme keywords.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"identity": {"name": "", "headline": "", "location": ""}, "core_skills": {"languages": [], "frameworks": [], "tools": []}, "experience": [{"company": "", "role": "", "dates": "", "highlights": []}], "featured_projects": [{"name": "", "themes": []}]}
