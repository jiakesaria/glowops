"""Learning → reviewed improvement → holdout, with resumable rounds."""
import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT, get_config
from run_tests import load_cases, run_evaluation, read_json, write_json, input_hashes
from improve import propose, status

os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".plot-cache"))

def draw_chart(history, path, fake):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    rounds = [r["round"] for r in history]
    fig, ax = plt.subplots(figsize=(9, 5.4), constrained_layout=True)
    fig.patch.set_facecolor("#f7f9fc")
    ax.set_facecolor("white")
    for split, color, label, offset, marker in (
        ("learn", "#2463a0", "Learning cases · before improvement", 8, "o"),
        ("holdout", "#b55222", "Holdout cases · after improvement", -17, "s"),
    ):
        values = [r[split]["accuracy"] for r in history]
        ax.plot(rounds, values, color=color, label=label, marker=marker, linewidth=2.2, markersize=7)
        for x, y in zip(rounds, values):
            ax.annotate(f"{y:.0%}", (x, y), textcoords="offset points", xytext=(0, offset), ha="center", color=color)
    ax.set_ylim(0, 1.06)
    ax.set_xlim(0.7, max(rounds) + 0.3)
    ax.set_xticks(rounds)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set_xlabel("Round")
    ax.set_ylabel("Decision agreement with draft answer key")
    ax.grid(axis="y", alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    title = "FAKE MODE — three-round integration check" if fake else "Three-round prototype evaluation"
    ax.set_title(title, loc="left", fontsize=15, pad=17, fontweight="bold")
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    note = ("Fixed offline responses. No model learning or improvement measured." if fake
            else "Repeated holdout monitoring; not an untouched final-confirmation evaluation.")
    fig.supxlabel(note + "\nScores measure decision agreement, not citation correctness or scientific truth.", fontsize=9, color="#465164")
    fig.savefig(path, dpi=170)
    plt.close(fig)

def save_aggregate(run, history, fake, output_root):
    write_json(run / "rounds_summary.json", {
        "mode": "fake" if fake else "real", "rounds": history,
        "interpretation": "Fixed-response wiring demo only." if fake else "Prototype monitoring with repeated holdout exposure; no fresh final-test claim.",
    })
    with (run / "accuracy_by_round.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["round", "split", "assigned", "matched", "mismatched", "errors", "accuracy"])
        for item in history:
            for split in ("learn", "holdout"):
                score = item[split]
                writer.writerow([item["round"], split, *[score[k] for k in ("assigned", "matched", "mismatched", "errors", "accuracy")]])
    draw_chart(history, run / "accuracy_by_round.png", fake)
    # Visible results contain only the latest outputs. Detailed history is hidden.
    for suffix in ("png", "csv"):
        target = output_root / f"accuracy_by_round.{suffix}"
        target.write_bytes((run / f"accuracy_by_round.{suffix}").read_bytes())
    write_json(output_root / "round_summary.json", read_json(run / "rounds_summary.json"))


def continue_run(run, state, review_complete=False):
    options = state['options']
    if state.get('input_sha256') != input_hashes():
        raise ValueError('Corpus, benchmark or implementation changed; start a new comparison run.')
    settings = get_config()
    # Keep fake lessons inside this run, never overwrite Sylvia's real lesson file.
    improvement_settings = settings.model_copy(update={'root': run}) if options['fake'] else settings
    model = 'fake' if options['fake'] else settings.model_id
    if model != options['model']:
        raise ValueError('Model changed since this run started; start a new run.')
    cases = load_cases(run / 'data/tests.json')
    while state['round'] <= options['rounds']:
        number = state['round']
        folder = run / f'round_{number:02d}'
        folder.mkdir(exist_ok=True)
        if state['phase'] == 'learn':
            print(f'Round {number}: learning cases', flush=True)
            # Round 1 begins without lessons; holdout uses this round's reviewed lessons.
            score = run_evaluation([c for c in cases if c.split == 'learn'], folder / 'learn',
                fake=options['fake'], with_jev=options['with_jev'], round_number=number - 1,
                timeout=options['timeout'])
            state['current'] = {'round': number, 'learn': score}
            if score['errors']:
                state['phase'] = 'error'
                write_json(run / 'state.json', state)
                raise RuntimeError('Learning calls failed; no lessons generated from API failures.')
            # Failure round identifies the lesson generation cycle, not prior lesson cutoff.
            failures = read_json(folder / 'learn/failures.json')
            for failure in failures:
                failure['round'] = number
            write_json(folder / 'failures.json', failures)
            if not options['fake']:
                write_json(ROOT / 'data/failures.json', failures)
            state['phase'] = 'improve'
            write_json(run / 'state.json', state)
        if state['phase'] == 'improve':
            print(f'Round {number}: proposing lessons', flush=True)
            proposals = propose(folder / 'failures.json', round=number,
                                settings=improvement_settings, fake=options['fake'])
            state['current']['improvement'] = {'proposed_lessons': len(proposals),
                'mode': 'fake' if options['fake'] else 'real', 'automatically_approved': False}
            state['phase'] = 'holdout' if options['fake'] or not proposals else 'review'
            write_json(run / 'state.json', state)
        if state['phase'] == 'review':
            pending = status(settings, model=model, round=number)
            if not review_complete or pending:
                print('Review lessons with improve.py list --pending, then approve or reject each proposal.')
                print('Resume: ' + shlex.join([sys.executable, str(ROOT / 'run_rounds.py'),
                      '--resume', str(run), '--review-complete']))
                return 3
            review_complete = False
            state['phase'] = 'holdout'
            write_json(run / 'state.json', state)
        if state['phase'] == 'holdout':
            print(f'Round {number}: holdout cases', flush=True)
            score = run_evaluation([c for c in cases if c.split == 'holdout'], folder / 'holdout',
                fake=options['fake'], with_jev=options['with_jev'], round_number=number,
                timeout=options['timeout'])
            state['current']['holdout'] = score
            if score['errors']:
                state['phase'] = 'error'
                write_json(run / 'state.json', state)
                raise RuntimeError('Holdout calls failed. Inspect the recorded errors before a new run.')
            state['history'].append(state['current'])
            save_aggregate(run, state['history'], options['fake'], ROOT / 'results')
            state['round'] += 1
            state['phase'] = 'complete' if state['round'] > options['rounds'] else 'learn'
            write_json(run / 'state.json', state)
    print(f"Completed {options['rounds']} rounds. Chart: {ROOT / 'results/accuracy_by_round.png'}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fake', action='store_true')
    parser.add_argument('--with-jev', action='store_true')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=150)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--review-complete', action='store_true')
    args = parser.parse_args(argv)
    try:
        import matplotlib
        matplotlib.use('Agg')
        if args.resume:
            state = read_json(args.resume / 'state.json')
            if state['phase'] not in ('review', 'complete'):
                raise ValueError('Only review checkpoints can resume; inspect failures before restarting.')
            return continue_run(args.resume.resolve(), state, args.review_complete)
        if args.review_complete or not 1 <= args.rounds <= 3 or args.timeout <= 0:
            raise ValueError('Use 1–3 rounds and a positive timeout; review-complete requires resume.')
        cases = load_cases(ROOT / 'data/tests.json')
        if {c.split for c in cases} != {'learn', 'holdout'}:
            raise ValueError('Both learning and holdout cases are required.')
        run = ROOT / 'results' / ('rounds_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        write_json(run / 'data/tests.json', [c.model_dump() for c in cases])
        state = {'round': 1, 'phase': 'learn', 'history': [], 'input_sha256': input_hashes(), 'options': {
            'fake': args.fake, 'with_jev': args.with_jev, 'rounds': args.rounds,
            'timeout': args.timeout, 'model': 'fake' if args.fake else get_config().model_id}}
        write_json(run / 'state.json', state)
        return continue_run(run, state)
    except Exception as exc:
        print(f'Rounds stopped ({type(exc).__name__}). Review run results and safe API telemetry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
