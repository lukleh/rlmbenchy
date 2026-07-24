"""Built-in workload loader registry."""

from __future__ import annotations

from rlmbenchy.datahub.types import WorkloadLoader


def builtin_workload_loaders() -> dict[str, WorkloadLoader]:
    from rlmbenchy.datahub.workloads.browsecomp_plus import (
        WORKLOAD_NAME as BROWSECOMP_PLUS_NAME,
        load_workload as browsecomp_plus_load,
    )
    from rlmbenchy.datahub.workloads.check_adapter_matrix import (
        WORKLOAD_NAME as CHECK_ADAPTER_MATRIX_NAME,
        load_workload as check_adapter_matrix_load,
    )
    from rlmbenchy.datahub.workloads.check_contract import (
        WORKLOAD_NAME as CHECK_CONTRACT_NAME,
        load_workload as check_contract_load,
    )
    from rlmbenchy.datahub.workloads.transcripts import (
        WORKLOAD_NAME as TRANSCRIPTS_NAME,
        load_workload as transcripts_load,
    )
    from rlmbenchy.datahub.workloads.longbench_codeqa import (
        WORKLOAD_NAME as LONGBENCH_CODEQA_NAME,
        load_workload as longbench_codeqa_load,
    )
    from rlmbenchy.datahub.workloads.longcot import (
        WORKLOAD_NAME as LONGCOT_NAME,
        load_workload as longcot_load,
    )
    from rlmbenchy.datahub.workloads.oolong import (
        WORKLOAD_NAME as OOLONG_NAME,
        load_workload as oolong_load,
    )
    from rlmbenchy.datahub.workloads.oolong_pairs import (
        WORKLOAD_NAME as OOLONG_PAIRS_NAME,
        load_workload as oolong_pairs_load,
    )
    from rlmbenchy.datahub.workloads.open_subtitles import (
        WORKLOAD_NAME as OPEN_SUBTITLES_NAME,
        load_workload as open_subtitles_load,
    )
    from rlmbenchy.datahub.workloads.s_niah import (
        WORKLOAD_NAME as S_NIAH_NAME,
        load_workload as s_niah_load,
    )
    from rlmbenchy.datahub.workloads.tasks_v0 import (
        WORKLOAD_NAME as TASKS_V0_NAME,
        load_workload as tasks_v0_load,
    )

    return {
        TASKS_V0_NAME: tasks_v0_load,
        CHECK_CONTRACT_NAME: check_contract_load,
        CHECK_ADAPTER_MATRIX_NAME: check_adapter_matrix_load,
        BROWSECOMP_PLUS_NAME: browsecomp_plus_load,
        OOLONG_NAME: oolong_load,
        OOLONG_PAIRS_NAME: oolong_pairs_load,
        LONGBENCH_CODEQA_NAME: longbench_codeqa_load,
        LONGCOT_NAME: longcot_load,
        OPEN_SUBTITLES_NAME: open_subtitles_load,
        S_NIAH_NAME: s_niah_load,
        TRANSCRIPTS_NAME: transcripts_load,
    }


__all__ = ["builtin_workload_loaders"]
