---
title: Research, Explainable Cyber-Physical Systems Lab
---

## My role in the lab

From January to June 2026, I was a research assistant in the Explainable Cyber-Physical Systems Lab, a Vanderbilt University affiliated lab in Nashville led by Dr. Meiyi Ma. I joined the lab for its focus on explainability: cyber-physical systems, software that senses and controls something in the physical world, are often built without proper trace logs or observable metrics, which makes it hard to understand why they did what they did, and adding AI to them makes that worse.

## What I built: an explainable traffic signal controller

My project, traffic-cps, is an explainable traffic signal controller for one simulated intersection. It was my own project, and its purpose was for me to learn more about cyber-physical systems, how their components are organized in a hierarchy, and ways to implement and improve explainability. I chose a traffic signal because it has exactly that hierarchy of components, a sensor that observes traffic, a controller that decides, and an actuator that changes the light, and because it is a natural place to apply intelligent systems. SUMO, an open-source traffic simulator, simulates the traffic, and my code controls the light directly through TraCI, SUMO's control interface, one simulated second at a time. Every observation, decision, light change, safety check, and learning update is recorded and can be explained afterward. The goal wasn't only to control the light well, but to be able to answer, for any moment in a run, why the light did what it did.

## Three controllers under the same rules

Three controllers run against identical traffic. Fixed-time switches the light after a tuned green duration. The queue rule gives green to the direction with the higher queue score, and keeps the current green on a tie. Tabular Q-learning learns a table of 200 traffic states, each with a value for keeping the current green or switching, and then runs with that table frozen for evaluation. What sets Q-learning apart is that it takes the future into account: for a decision made now, such as whether to change the light, it weighs how congestion is likely to get better or worse afterward. Because that is how it decides, it is constantly looking for the choices that reduce congestion over time, not just right now. All three are held to the same operating rules: a 2-second yellow, a 5-second minimum green, and a 60-second limit on how long one direction can hold green. An independent safety monitor checks every signal change any controller makes, so no controller can break those rules, whatever it decides.

## Making the explanations faithful, not just plausible

To me, a faithful explanation is one based on evidence. An explanation is only useful if it describes how the decision was actually made, so each decision is explained from the evidence that produced it. Before an explanation is shown, a fidelity check re-runs the recorded rule on the recorded numbers and confirms it produces the same decision. For Q-learning, that means using the exact table the controller had at that moment, which is rebuilt from the run's starting table plus every learning update logged since. Every decision also states its alternative, "why this rather than that": the queue-rule threshold, the fixed-time switch point, or the nearest queue situation that would have flipped the learned choice.

Explanations can be read without digging through logs: explain and summarize commands on the command line, and an offline HTML report for each run with a queue and signal timeline, decision markers colored by which controller logic produced them, and the learned policy drawn as grids. I'm careful about what this shows. The fidelity checks prove the explanations match the decision process. They don't show that people understand the controller better, because no user study was run.

## Results

On five held-out one-hour scenarios, the queue rule had the lowest mean queue, 5.12 vehicles, ahead of tuned fixed-time at 9.59 and the Q-learning policy trained for 15 episodes at 11.46. Adding low sensor noise had no measurable effect. Every one of the 23,487 explanations generated passed the fidelity check.

## Reproducibility

Experiments are built to be repeated exactly. SUMO 1.24.0 runs in a Linux Docker container, because the macOS build of that version depends on Homebrew library versions that are no longer published, and a doctor command verifies the pinned toolchain before anything runs. Each run gets its own directory that is never overwritten, holding the resolved configuration, scenario and run manifests, the starting policy, a JSONL event log with one record per line, SUMO's own log, the HTML report, a summary, and metrics. Training saves checkpoints and can resume from them, and stopping a run partway finishes the current simulated second and saves whatever learning has completed.

## Limitations

This is one synthetic two-lane intersection with straight-through traffic only: no turns, pedestrians, all-red clearance intervals, or real demand data. The simulation moves in discrete one-second steps, and sensing reads the simulator's ground truth except in the labeled noise experiment. Five evaluation scenarios are initial evidence, not statistical significance, and the controller is not suitable for deployment on a real road.
