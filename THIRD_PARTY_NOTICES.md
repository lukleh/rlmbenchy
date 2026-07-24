# Third-Party Notices

## Recursive Language Models paper

The following files are derived from the paper *Recursive Language Models* by
Alex L. Zhang, Tim Kraska, and Omar Khattab:

- `docs/reference/2512.24601v2.md`
- `docs/reference/_page_*` image files
- `docs/reference/2512.24601v3.md`
- `docs/reference/2512.24601v3_assets/` image files

Sources:

- [arXiv:2512.24601v2](https://arxiv.org/abs/2512.24601v2)
- [arXiv:2512.24601v3](https://arxiv.org/abs/2512.24601v3)

License: [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)

Changes made for this repository: the source PDFs were converted to Markdown,
formatting was cleaned up, and figures were extracted or re-encoded. Conversion
errors may remain. The derived text and images are provided under CC BY 4.0.
Their inclusion does not imply endorsement by the paper's authors.

## Dataset integrations

The repository contains adapters for the following remote datasets. Dataset
contents are not bundled or redistributed here; they are fetched from upstream
when a workload is used. Users remain responsible for complying with the
upstream terms. License metadata and revisions below were checked on
2026-07-15.

| Dataset | Observed upstream revision | Upstream license metadata |
|---|---|---|
| [BrowseComp-Plus](https://huggingface.co/datasets/Tevatron/browsecomp-plus) | `144cff8e35b5eaef7e526346aa60774a9deb941f` | MIT |
| [LongBench-v2](https://huggingface.co/datasets/zai-org/LongBench-v2) | `2b48e494f2c7a2f0af81aae178e05c7e1dde0fe9` | Apache-2.0 |
| [LongCoT](https://huggingface.co/datasets/LongHorizonReasoning/longcot) | `7f9948570f5239f0f3697c6c9793b4866860c681` | MIT |
| [OOLONG synthetic](https://huggingface.co/datasets/oolongbench/oolong-synth) | `f0d59eaf0febf130664cfceb710436c8e3216b2b` | No license declared in the dataset card |
| [OpenSubtitles](https://huggingface.co/datasets/Helsinki-NLP/open_subtitles) | `6a1ddce6f2173f08c7d316736086d411fb155e65` | `unknown` in the dataset card; also subject to the [OPUS/OpenSubtitles source terms](https://opus.nlpl.eu/legacy/OpenSubtitles-v2018.php) |

The observed revisions are an audit record, not runtime pins; upstream default
branches may change. Relevant benchmark publications include
[BrowseComp-Plus](https://arxiv.org/abs/2508.06600),
[LongBench-v2](https://arxiv.org/abs/2412.15204),
[LongCoT](https://arxiv.org/abs/2604.14140), and
[OOLONG](https://arxiv.org/abs/2511.02817).

Because OOLONG and OpenSubtitles do not publish a clear dataset license in the
referenced dataset cards, their adapters should be used only after the user has
reviewed the upstream terms and determined that their intended use is allowed.
