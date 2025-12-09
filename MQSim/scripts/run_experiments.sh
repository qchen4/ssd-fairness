#!/usr/bin/env bash

# Automated experiment harness for comparing MQSim scheduler policies.
# The script loops over a set of workloads and scheduling policies, runs MQSim,
# and stores every result/log under results/<timestamp>/<policy>/<workload>/.

set -euo pipefail

# --- Configuration ---------------------------------------------------------
# Script should be run from MQSim root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQSIM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${MQSIM_ROOT}"

BASE_CONFIG="configs/ssdconfig.xml"
MQSIM_BIN="./MQSim"
RESULT_ROOT="results"

# Default workloads (relative to MQSim root)
WORKLOADS=(
  "workloads/workload_scenario_1.xml"
  "workloads/workload_scenario_2.xml"
  "workloads/workload_scenario_3.xml"
  "fast18/backend-contention/workload-backend-contention-flow-1-flow-2.xml"
  "fast18/backend-contention/workload-backend-contention-flow-1.xml"
  "fast18/backend-contention/workload-backend-contention-flow-2.xml"
  # "fast18/data-cache-contention/workload-datacache-contention-flow-1-flow-2.xml"  # Known issue: FPE on scenario 3
  "fast18/data-cache-contention/workload-datacache-contention-flow-1.xml"
  "fast18/data-cache-contention/workload-datacache-contention-flow-2.xml"
  "fast18/queue-fetch-size/workload-queue-fetch-size-flow-1-flow-2.xml"
  "fast18/queue-fetch-size/workload-queue-fetch-size-flow-1.xml"
  "fast18/queue-fetch-size/workload-queue-fetch-size-flow-2.xml"
  "workloads/workload_stress_bully_victim.xml"
  "workloads/workload_stress_multiqueue.xml"
  "workloads/workload_stress_rw_interference.xml"
)

# Policies to compare (5 schedulers)
POLICIES=(
  "RR"
  "DRR"
  "QFQ"
  "MINMAX"
  "FLIN"
)
# ---------------------------------------------------------------------------

timestamp="$(date +"%Y%m%d-%H%M%S")"
RUN_ROOT="${RESULT_ROOT}/${timestamp}"

ensure_compiled() {
  if [[ ! -x "${MQSIM_BIN}" ]]; then
    echo "MQSim binary not found; compiling via make..."
    make
  fi
}

set_policy_in_config() {
  local config_file=$1
  local policy=$2
  sed -i -E "s#<Transaction_Scheduling_Policy>[^<]*</Transaction_Scheduling_Policy>#<Transaction_Scheduling_Policy>${policy}</Transaction_Scheduling_Policy>#" "${config_file}"
}

collect_outputs() {
  local dest_dir=$1
  local workload_path=$2
  mkdir -p "${dest_dir}"

  # Copy known MQSim outputs deterministically to avoid cross-run races in parallel mode.
  local base_no_ext="${workload_path%.*}"

  # Copy scenario XMLs (default MQSim naming).
  shopt -s nullglob
  local xmls=( "${base_no_ext}_scenario_"*.xml )
  for path in "${xmls[@]}"; do
    cp "${path}" "${dest_dir}/"
    rm -f "${path}"
  done

  # Copy MQSim_Results* and *_results* if present.
  local extras=( MQSim_Results* *_results *_results.zip )
  for path in "${extras[@]}"; do
    [[ -e "${path}" ]] || continue
    if [[ -f "${path}" ]]; then
      cp "${path}" "${dest_dir}/"
      rm -f "${path}"
    elif [[ -d "${path}" ]]; then
      local base="$(basename "${path}")"
      rsync -a "${path}/" "${dest_dir}/${base}/"
      rm -rf "${path}"
    fi
  done
  shopt -u nullglob
}

run_single_experiment() {
  local policy=$1
  local workload=$2
  local scenario_name
  scenario_name="$(basename "${workload}" .xml)"
  local dest_dir="${RUN_ROOT}/${policy}/${scenario_name}"
  local tmp_config
  tmp_config="$(mktemp "${dest_dir//\//_}.XXXX.xml")"

  cp "${BASE_CONFIG}" "${tmp_config}"
  set_policy_in_config "${tmp_config}" "${policy}"

  mkdir -p "${dest_dir}"
  echo ""
  echo "=== ${policy} :: ${scenario_name} ==="
  if [[ ! -f "${workload}" ]]; then
    echo "Workload file '${workload}' not found!" >&2
    exit 1
  fi

  set +e
  "${MQSIM_BIN}" -i "${tmp_config}" -w "${workload}" | tee "${dest_dir}/run.log"
  local run_status=$?
  set -e
  rm -f "${tmp_config}"
  if [[ ${run_status} -ne 0 ]]; then
    echo "MQSim failed for ${policy}/${scenario_name} (continuing...)" >&2
    # Continue with next experiment instead of exiting
    return 1
  fi

  collect_outputs "${dest_dir}" "${workload}"
}

package_results() {
  local zip_name="${RESULT_ROOT}/${timestamp}.zip"
  ( cd "${RESULT_ROOT}" && zip -rq "${timestamp}.zip" "${timestamp}" )
  echo ""
  echo "Archived results at ${zip_name}"
}

main() {
  WORKLOAD_JOBS=${WORKLOAD_JOBS:-1}
  ensure_compiled
  mkdir -p "${RUN_ROOT}"

  for policy in "${POLICIES[@]}"; do
    echo ""
    echo "== Policy ${policy} (concurrency: ${WORKLOAD_JOBS}) =="
    job_count=0
    for workload in "${WORKLOADS[@]}"; do
      run_single_experiment "${policy}" "${workload}" &
      job_count=$((job_count + 1))
      if (( job_count >= WORKLOAD_JOBS )); then
        wait -n || exit 1
        job_count=$((job_count - 1))
      fi
    done
    # Wait for remaining jobs of this policy
    wait || exit 1
  done

  if [[ -f "tools/summarize_results.py" ]]; then
    echo ""
    echo "Generating summary CSV..."
    python3 tools/summarize_results.py --root "${RUN_ROOT}" || echo "Warning: summary generation failed"
  fi

  package_results
  echo "All experiments stored under ${RUN_ROOT}"
}

main "$@"