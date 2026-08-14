// Sample templates for the workspace's "what belongs here?" panel.
// Deliberately a COHERENT set: Sam Okafor appears in all five, so staging
// everything and pressing Run is a one-click demonstration of cross-source
// merging, provenance, the profile-URL link keys, and the portfolio rule.

const RECRUITERS_CSV = `name,email,phone,current_company,title
Sam Okafor,sam.okafor@example.com,+1 415 555 2671,Nimbus Analytics,Data Engineer
Priya Raman,priya.raman@example.com,,Vertex Labs,ML Engineer
`;

const ATS_JSON = `{
  "candidates": [
    {
      "candidateName": "Sam Okafor",
      "emailAddress": "sam.okafor@example.com",
      "currentEmployer": "Nimbus Analytics",
      "designation": "Senior Data Engineer",
      "skills": ["Python", "SQL", "Airflow"],
      "workHistory": [
        {"org": "Nimbus Analytics", "role": "Senior Data Engineer",
         "from": "2022-04", "to": "Present"}
      ],
      "city": "Austin",
      "country": "United States",
      "lastUpdated": "2026-07-01",
      "profileUrls": ["https://github.com/samokafor",
                      "https://www.linkedin.com/in/samokafor"]
    }
  ]
}
`;

const NOTES_TXT = `Name: Sam Okafor

Met at the data meetup - sharp on Python and Kafka. sam.okafor@example.com
Senior Data Engineer at Nimbus Analytics since Apr 2022.
`;

const GITHUB_JSON = `{
  "login": "samokafor",
  "name": "Sam Okafor",
  "bio": "Data pipelines and platform work",
  "html_url": "https://github.com/samokafor",
  "blog": "https://samokafor.dev",
  "email": null,
  "location": "Austin, United States",
  "languages": {"Python": 12, "Go": 3}
}
`;

const LINKEDIN_JSON = `{
  "fullName": "Sam Okafor",
  "headline": "Senior Data Engineer at Nimbus Analytics",
  "publicProfileUrl": "https://www.linkedin.com/in/samokafor",
  "location": {"city": "Austin", "country": "United States"},
  "positions": [
    {"companyName": "Nimbus Analytics", "title": "Senior Data Engineer",
     "startDate": {"year": 2022, "month": 4}, "isCurrent": true}
  ],
  "educations": [
    {"schoolName": "University of Lagos", "degreeName": "B.Sc",
     "fieldOfStudy": "Computer Science", "endYear": 2015}
  ]
}
`;

export const SOURCE_ROWS = [
  {
    icon: "csv", pattern: "recruiters.csv",
    why: "Recruiter CSV export — rows of name/email/phone/company/title",
    template: { name: "recruiters.csv", content: RECRUITERS_CSV },
  },
  {
    icon: "json", pattern: "ats.json",
    why: "ATS JSON blob — its own field names, mapped declaratively by the adapter",
    template: { name: "ats.json", content: ATS_JSON },
  },
  {
    icon: "txt", pattern: "notes_*.txt",
    why: "Recruiter notes — free text; rule-extracted, one candidate per file",
    template: { name: "notes_sample.txt", content: NOTES_TXT },
  },
  {
    icon: "resume", pattern: "resume_*.docx / *.pdf",
    why: "Resumes — text extracted, then the same rules as notes. Drop any real one.",
    template: null, // a fabricated binary teaches nothing — bring a real file
  },
  {
    icon: "github", pattern: "github_<login>.json",
    why: "GitHub profile — recorded API payload (tools/fetch_github.py records "
      + "it once; live fetch stays out of the pipeline, ADR-002/017)",
    template: { name: "github_samokafor.json", content: GITHUB_JSON },
  },
  {
    icon: "linkedin", pattern: "linkedin_<slug>.json",
    why: "LinkedIn profile — recorded export payload (no sanctioned live API)",
    template: { name: "linkedin_samokafor.json", content: LINKEDIN_JSON },
  },
];

/** btoa for possibly-non-ASCII template text. */
export function textToB64(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  return btoa(bin);
}
