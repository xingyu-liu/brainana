# License and Copyright

This document gives a **license decision summary** (current situation, two options, recommendation) and then lists all parts of the brainana codebase that mention **copyright**, **license**, **reuse**, or **attribution**.

---

## License decision summary

### Current situation

| Component | Current / upstream license | Notes |
|-----------|----------------------------|--------|
| **Repository** | TBD (root `LICENSE`) | Not yet decided. |
| **nhp_skullstrip_nn** | No header in code | **Derived from NHP-BrainExtraction → upstream is AGPL-3.0** |
| **fastsurfer_nn / fastsurfer_surfrecon** | Apache 2.0 | DZNE; permissive |

So: root license is TBD, one subpackage is an AGPL derivative (nhp_skullstrip_nn), and FastSurfer code is Apache 2.0.

---

### Option 1: AGPL-3.0 (entire project)

**What you do:** One license for the whole repo. Replace root `LICENSE` with AGPL-3.0. Keep existing Apache 2.0 **notices** for FastSurfer files; the project as a whole is AGPL-3.0.

**Pros:** Single license; clear; satisfies NHP-BrainExtraction; strong copyleft; fine for non-profit.  
**Cons:** Some orgs avoid AGPL; if someone runs a *modified* brainana as a network service, they must offer that version’s source.

**Best if:** You want one clear rule and are okay with strong copyleft for the whole project.

---

### Option 2: Dual — AGPL-3.0 (nhp_skullstrip_nn) + Apache 2.0 (rest)

**What you do:**
- **nhp_skullstrip_nn:** Under AGPL-3.0 (package-level LICENSE or header; state “Adapted from NHP-BrainExtraction, AGPL-3.0”).
- **Rest of brainana:** Apache 2.0. Root `LICENSE` is Apache 2.0, with a short “Exceptions” note: the package `nhp_skullstrip_nn` is under AGPL-3.0 (see that package / upstream NHP-BrainExtraction).

**Pros:** Rest of brainana is permissive (Apache 2.0); only the skullstrip component is AGPL; often easier for institutions that restrict AGPL.  
**Cons:** You must keep “which part is which license” clearly documented.

**Best if:** You want maximum reuse of the pipeline/core and only the NHP-BrainExtraction–derived part under AGPL.

---

### Quick comparison

| | Option 1: Full AGPL-3.0 | Option 2: Dual (AGPL + Apache 2.0) |
|--|------------------------|-------------------------------------|
| **Clarity** | One license | Two; need clear docs |
| **Copyleft** | Whole project | Only nhp_skullstrip_nn |
| **Reuse of “the rest”** | Must stay AGPL | Can be used under Apache 2.0 |
| **Compliance with NHP-BrainExtraction** | Yes | Yes (for that package) |
| **Non-profit friendly** | Yes | Yes |

---

### Recommendation in one line

- Prefer **one rule and strong “give back”** → **Option 1 (AGPL-3.0 entire project)**.  
- Prefer **maximum permissiveness for everything except skullstrip** → **Option 2 (dual: AGPL for nhp_skullstrip_nn, Apache 2.0 for the rest)**.

---

</br>
</br>


## Copyright decision summary

### What is copyright?

**Copyright** is the legal right of the author of a work (code, text, images, etc.) to control copying, distribution, and modification. In most countries it arises **automatically** when you create something: you don’t have to register or add a notice for the work to be protected (though registration can help in some places for enforcement).

For **software**:
- **You** own the copyright on code you write (unless you assigned it to an employer or other entity).
- **Others** own the copyright on their code (e.g. NHP-BrainExtraction, DZNE/FastSurfer). You can only use it under their **license** (e.g. AGPL, Apache 2.0).
- A **license** is the permission you give (or they give you) to use, copy, modify, and distribute the work under certain conditions.

So: **copyright = who owns it**. **License = what others are allowed to do with it.**

### What you should do for brainana (practical)

**1. Decide who the “copyright holder” is**

- **Person:** e.g. “Copyright (c) 2024 Jane Doe” (or 2024–2025 if you keep updating).
- **Institution:** e.g. “Copyright (c) 2024 University of X” or “Copyright (c) 2024 CEA.”
- **Multiple:** e.g. “Copyright (c) 2024 Jane Doe, University of X.”

You only need **one** canonical statement (e.g. in `LICENSE` and/or README). Use the name of the legal entity that should own the work (you, your lab, your employer, etc.).

**2. Put the copyright notice where it matters**

Once you pick a license (AGPL or dual, as above), the **LICENSE** file will include a “Copyright (c) YEAR NAME” line. That’s the main place. Optionally you can also:

- Add one line in the **README**: e.g. “Copyright (c) 2024 [Name]. See LICENSE.”
- Add a short header in **key source files** (e.g. main `__init__.py` or entrypoints): e.g.  
  `# Copyright (c) 2024 [Name]. Licensed under AGPL-3.0.`

You don’t have to put a notice in every file; one clear notice in LICENSE (and maybe README) is enough for most projects.

**3. Don’t remove others’ copyright notices**

- **FastSurfer (DZNE):** Their files already have “Copyright (c) 20XX Image Analysis Lab, DZNE” and Apache 2.0. **Keep those headers** when you use their code.
- **NHP-BrainExtraction:** You’re not shipping their code verbatim; you’re adapting the approach in `nhp_skullstrip_nn`. You **must** keep their **license** (AGPL-3.0) and **attribution** (that your code is adapted from NHP-BrainExtraction). You don’t need to copy their exact copyright line into your files, but your LICENSE or a “Third-party / Attributions” section should state that `nhp_skullstrip_nn` is adapted from NHP-BrainExtraction (AGPL-3.0). That’s what you’ve already documented.

**4. Year**

Use the year you first publish or release the project (e.g. 2024). If you update the project in later years, some people use “2024–2025”; it’s optional. One year is fine.

**5. What you don’t need to do**

- You don’t need to **register** copyright for the license to be valid (unless you’re in a jurisdiction where you want extra enforcement tools).
- You don’t need a lawyer to add “Copyright (c) YEAR Name” and a license; that’s standard practice.
- You don’t need to change the **content** of DZNE’s or NHP-BrainExtraction’s notices; just keep them and add your own for **your** code.

### Checklist for brainana

| Step | Action |
|------|--------|
| 1 | Decide copyright holder: you, your institution, or both. |
| 2 | Choose license (Option 1: full AGPL, or Option 2: dual AGPL + Apache 2.0) from above. |
| 3 | Replace root `LICENSE` with the full text of the chosen license(s) and add: **Copyright (c) YEAR Name** (or names). |
| 4 | Optionally add one line in README: “Copyright (c) YEAR Name. See LICENSE.” |
| 5 | Keep all existing DZNE and NHP-BrainExtraction notices and attributions; add a short “Attributions” or “Third-party” section in README or LICENSE if you use Option 2 (dual license). |
| 6 | In `pyproject.toml`, set `license = {text = "AGPL-3.0"}` (or the correct identifier) and add the right classifier once you’ve decided. |
