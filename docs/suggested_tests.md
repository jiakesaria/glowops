# Suggested Test Hypotheses

Ten test hypotheses for the Hypothesis Validity Checker, one per paper in `sources.md`.

They are a deliberate mix. Most are reasonable extensions of a paper that the checker should let through. Some have problems the checker should catch. Each one lists the verdict we expect, so it can be scored.

## Summary

| # | Based on | Hypothesis (short) | Expected verdict |
|---|----------|--------------------|------------------|
| 1 | Braithwaite & Lemke (2011) | Land disputes escalate even between non-neighbors | Proceed |
| 2 | Carlson (1995) | Countries that can't handle long fights strike hard early | Revise |
| 3 | Fearon (1994) | Democracies back down less often in crises | Reject (already tested) |
| 4 | Fearon (1995) | Wars happen because countries fail to make a deal | Reject (not falsifiable) |
| 5 | Gartzke (2007) | Rich market economies fought each other less before 1945 too | Proceed |
| 6 | Kinsella & Russett (2002) | Neighbors start more disputes, but those disputes don't turn into wars more often | Proceed |
| 7 | Quek (2016) | Moving troops doesn't make the other side back down more than threats alone | Proceed |
| 8 | Slantchev (2005) | Spending more on the military during a crisis makes war less likely | Revise |
| 9 | Tang (2026) | Leaders who back down from threats aren't more likely to lose power | Proceed |
| 10 | Weeks (2008) | Most dictatorships make threats as believable as democracies do | Reject (already tested) |

**Verdicts used:**
- **Proceed:** clear, testable with data we can get, and adds something new.
- **Revise:** the idea is worth testing, but the wording or the data has a problem that needs fixing first.
- **Reject:** can't be proven true or false, or has already been tested enough.

---

## 1. Land disputes and distance

- **Based on:** Braithwaite & Lemke (2011)
- **Hypothesis:** Disputes over land are more likely to get violent than other disputes, even when the two countries don't share a border.
- **What's new:** The paper found territory matters. This checks whether that is just because land disputes usually happen between neighbors.
- **Data needed:** MID dataset (what the dispute was about, how violent it got), CoW Direct Contiguity (who borders whom)
- **Expected verdict:** Proceed

## 2. Low pain tolerance and striking first

- **Based on:** Carlson (1995)
- **Hypothesis:** Countries that can't handle a long, costly fight tend to hit as hard as they can at the very start of a dispute.
- **What's wrong:** "Can't handle a long fight" isn't something any dataset measures directly.
- **Better version:** Pick something measurable to stand in for it, such as a country's military size or economic output compared to its rival.
- **Expected verdict:** Revise

## 3. Democracies backing down

- **Based on:** Fearon (1994)
- **Hypothesis:** Once a crisis starts, democracies are less likely to back down than non-democracies.
- **What's wrong:** This is the main prediction of the audience costs theory. It has been tested many times, and Weeks (2008) and Tang (2026) both review that evidence.
- **Expected verdict:** Reject (already tested)

## 4. Failed deals cause war

- **Based on:** Fearon (1995)
- **Hypothesis:** Wars happen because countries fail to reach a deal they would both prefer to fighting.
- **What's wrong:** Every war is a failed deal by definition, so there is no outcome that could prove this wrong. A testable version would name a specific cause, for example "wars are more likely when one side's military power is growing fast."
- **Expected verdict:** Reject (not falsifiable)

## 5. The capitalist peace before 1945

- **Based on:** Gartzke (2007)
- **Hypothesis:** Pairs of economically developed countries were less likely to fight each other than other pairs even before 1945, not just after.
- **What's new:** Gartzke focuses on the period after WWII. CoW data goes back to 1816, so we can check whether the pattern holds earlier.
- **Data needed:** CoW National Material Capabilities (energy use and industry as a measure of development), MID dataset
- **Caveat:** Good data on financial markets before 1945 is thin, so this would test the development part of the argument only.
- **Expected verdict:** Proceed

## 6. Neighbors, disputes, and wars

- **Based on:** Kinsella & Russett (2002)
- **Hypothesis:** Neighboring countries get into disputes more often, but once a dispute starts, being neighbors doesn't make it more likely to become a war.
- **What's new:** It splits the effect of geography into two steps: starting a dispute and escalating it. The paper hints at this, and it can be tested back to 1816.
- **Data needed:** CoW Direct Contiguity, MID dataset, CoW War data
- **Expected verdict:** Proceed

## 7. Troops vs. words

- **Based on:** Quek (2016)
- **Hypothesis:** In real disputes, countries that move troops are no more likely to get the other side to back down than countries that only make verbal threats.
- **What's new:** Quek found this gap in a lab experiment. This checks whether it shows up in real history.
- **Data needed:** MID dataset (it records whether a country only threatened, showed force, or used force, and which side gave in)
- **Expected verdict:** Proceed

## 8. Military spending and peace

- **Based on:** Slantchev (2005)
- **Hypothesis:** When countries spend more on their military during a crisis, the crisis is less likely to end in war.
- **What's wrong:** CoW records military spending only once a year, which is too coarse to show what happened during a crisis that lasted a few weeks.
- **Better version:** Use troop mobilizations recorded in the MID dataset instead of yearly spending.
- **Expected verdict:** Revise

## 9. Do leaders pay for backing down?

- **Based on:** Tang (2026)
- **Hypothesis:** Leaders who back down after making a public threat are no more likely to lose power within the next year than leaders who never made a threat.
- **What's new:** Tang reviews individual case studies. This tests the same question across hundreds of leaders.
- **Data needed:** Archigos (dates and ways leaders left office), MID dataset
- **Note:** Archigos is not part of CoW, but it is free and widely used.
- **Expected verdict:** Proceed

## 10. Dictatorships and believable threats

- **Based on:** Weeks (2008)
- **Hypothesis:** Military regimes and one-party states make threats that are just as believable as threats from democracies.
- **What's wrong:** This restates the paper's own main finding, so it has already been tested.
- **Expected verdict:** Reject (already tested)