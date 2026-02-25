from resume_indexing_agent import resume_indexing_agent
from job_description_agent import run_jd_matching

print("\n🚀 ATS AI AGENTS STARTED")

try:

    print("\n📄 STEP 1 → Resume Indexing Agent")
    resume_indexing_agent()

    print("\n🎯 STEP 2 → JD Matching Agent")
    run_jd_matching()

    print("\n✅ ALL AGENTS FINISHED SUCCESSFULLY")

except Exception as e:
    print("\n❌ AGENT ERROR:", e)