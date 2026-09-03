# Blueprint Split Manifest
GENERATED FROM: LOCAL_SOC_SLM_Blueprint_v11.11
MASTER SHA256: (current HEAD: ab8067b)
FILES WRITTEN: 25+
TOTAL LINES: 4327+

## Reassembly Rule
The canonical source of truth is now the split file structure.
The master files (LOCAL_SOC_SLM_Blueprint_v11.6.0 through v11.9.0_master.txt)
have been superseded by v11.11 and are deprecated.

THE SPLIT FILES ARE NOW CANONICAL:
- sections/ (s30-s38)
- amendments/ (AMEND-1 through AMEND-52+)
- appendices/ (M-Q)
- checklists/
- _frontmatter.md
- _changelog.md

Any amendment, correction, or expansion must be applied directly to
these split files. The old master files are retained in git history
only for archival purposes.

## File Map
- _frontmatter.md
- amendments/amend_v11.3_001-013.md
- amendments/amend_v11.4_014-026.md
- amendments/amend_v11.5_027-036.md
- amendments/amend_v11.5.1_037-041.md
- amendments/amend_v11.5.2_042-046.md
- amendments/amend_v11.6.0_047-052.md
- sections/s30_orchestration_memory.md
- sections/s31_continual_learning.md
- sections/s32_deployment_readiness.md
- sections/s33_inference_vram.md
- sections/s34_sanitization_quarantine.md
- sections/s35_async_ingestion_backpressure.md
- sections/s36_vector_memory_lifecycle.md
- sections/s37_hash_chain_audit.md
- sections/s38_knowledge_wiki.md
- appendices/appendix_m_docs_index.md
- appendices/appendix_n_research_register.md
- appendices/appendix_o_ci_tools.md
- appendices/appendix_p_templates.md
- appendices/appendix_q_runbooks.md
- checklists/release_checklist_v11.11.md
- checklists/completeness_manifest.md
- _changelog.md

[Rest of the file stays exactly the same - keep all the cross-references and loading recipes]
