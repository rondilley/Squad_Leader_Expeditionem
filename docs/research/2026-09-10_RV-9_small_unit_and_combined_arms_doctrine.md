# RV-9: Small-unit and combined-arms doctrine for the computer opponents

Date: 2026-09-10
Project: Squad_Leader_AI
Scope: real military small-unit and combined-arms doctrine, turned into decisions for the game's computer opponents (scripted v4, learned agents, prompted model agents).

## Purpose and scope

This appendix turns real military doctrine into decisions for the game's computer opponents. It merges four universal doctrine sources (US Army FM 3-90 offense and defense, USMC MCDP 1-3, and a web-verified set of primary US infantry and armor manuals) into one prioritized list of tactics, and it adds national profiles and a doctrine-breaking idea library. Each principle maps to the engine: an agent picks one legal command per decision frame, so a principle is only useful when it is a computable rule against the game state (a threat and line of sight map, a fire group firepower against a target defense value, a flank or rear direction, and whether a hex gives cover). The two tables at the end are the build spec: a principle to game lever to v4 heuristic to reinforcement learning reward term map, and a nation to behavioral bias map.

## 1. Rules of evidence

- Each principle names its source by manual and paragraph or page, or by author and work. The four universal digests are in `background/doctrine_notes/` (a git-ignored working area).
- FM 3-90 is a public United States Government work; MCDP 1-3 is public release. The web set passed a 3 to 0 adversarial check against primary manuals (FM 3-21.8, ATP 3-21.8, FM 7-10, FM 17-15, FM 3-22.68, ATP 3-20.15). Three of those manuals are legacy editions; the cited doctrine (final protective line, final protective fire, grazing fire, reverse slope, engagement areas, bound length) is stable across editions.
- The words here are the project's own. No manual text is copied.
- The national research has asymmetric coverage. The caveats and the refuted claims are stated in section 3, not hidden.

## 2. Universal small-unit and combined-arms tactics

This is a prioritized list. The highest-leverage principles for a win against a strong human are first. The order comes from three facts about the engine: fire is non-linear (a big fire group reaches a better table column than the same units split up), the phase order rewards the side that suppresses before it moves, and cover plus concealment plus flank direction let a weaker-firepower side win. The list merges duplicates across the four universal sources; a merged principle names all of its sources.

There are 22 principles.

### P1. Suppress before you move; fire and movement are one act

- Doctrine: A moving element crosses open ground only after fire holds down the enemy that can shoot it. Fire enables movement and movement enables more fire.
- Mechanism: A pinned or broken defender fires at reduced effect or not at all, so the mover crosses at a lower loss rate.
- Source: FM 3-90 offense para 5-65, 5-74; web set finding 1 and 3 (FM 3-21.8: fire and movement win engagements; ATP 3-21.8: suppressive fires facilitate movement).
- In the game, the agent should form a fire group in prep fire against the enemy that covers the maneuver path, get a pin or break, and only then move the assault stack; it keeps the base of fire firing while the mover is exposed.

### P2. Concentrate fire on one critical target; do not spread and do not overkill

- Doctrine: Mass the effects of fire at one point. Destroy the greatest threat first, then shift; do not add firepower past the break threshold.
- Mechanism: The fire table is non-linear, so one combined group against one hex beats the same units against separate hexes. The one unit that props up a position (a leader, a machine gun) collapses more than its own hex.
- Source: FM 3-90 offense para 1-113 to 1-117, 5-18; MCDP 1-3 ch.2 (critical vulnerability, PDF p.40).
- In the game, the agent should combine all units with line of sight and range into one fire group against the single highest-value enemy (a leader, a support weapon, the unit covering the assault lane), and once that target is at break odds, shift surplus firepower to the next threat.

### P3. Base of fire versus maneuver element; present a dilemma

- Doctrine: Split the force. One part is the base of fire that suppresses; the other part is the assault that closes. Combine weapons so every enemy answer to one threat exposes him to the other.
- Mechanism: One element fixes while the other moves; a pinned defender can neither hold nor stop the assault, and an unpinned defender that fires reveals and exposes itself.
- Source: FM 3-90 offense para 5-70 to 5-74, 2-38 to 2-40; MCDP 1-3 ch.3 (combined arms, PDF p.49 to p.51).
- In the game, the agent should keep one stack with line of sight to the objective firing (the base of fire) while a separate stack advances, and time the base-of-fire fire against the objective to coincide with the assault stack's approach.

### P4. Strike the flank or rear; avoid the front

- Doctrine: Avoid the enemy front, where fire and cover are strongest, and attack the flank or rear, where the defender is weaker and oriented the wrong way. The frontal attack is the least favored form; use it only to overwhelm or only to fix.
- Mechanism: Cover and firepower are directional; a flank or rear approach meets weaker fire, and in close combat and against armor it meets weaker defense.
- Source: FM 3-90 offense para 2-58 to 2-59, 2-27 to 2-35, 5-59; MCDP 1-3 ch.3 (complementary forces, PDF p.56).
- In the game, the agent should route the maneuver element to fire or close combat from the enemy flank or rear hex, and against an armored vehicle should move into the covered arc that presents flank or rear armor; a frontal assault is allowed only when the break probability is high.

### P5. Fix the larger part, mass against the weak part

- Doctrine: Fix with the minimum combat power so the enemy cannot reposition, and mass the bulk against one chosen weak point. Local superiority, not global superiority, decides each fight.
- Mechanism: A defender who cannot shift reserves fights the assault locally outnumbered.
- Source: FM 3-90 offense para 5-53 to 5-55, 3-19, 5-18; MCDP 1-3 ch.2 (main effort and economy of force, PDF p.42 to p.43).
- In the game, the agent should hold part of the enemy line with harassing prep fire that threatens a check, while stacking a firepower and unit majority against one target hex to cross the favorable-odds column.

### P6. Designate and support one main effort each turn

- Doctrine: Each turn pick one decisive action as the main effort and weight it with the best leader, the largest fire groups, smoke, and armor; use the minimum elsewhere; re-tag the main effort toward the sector that actually opens.
- Mechanism: Concentrated support produces a breakthrough; scattered support produces indecision. The main effort can shift as the game opens.
- Source: MCDP 1-3 ch.2 (main effort and economy of force, PDF p.42 to p.43).
- In the game, the agent should each turn tag one objective-relevant action as the main effort, route its best leader and largest fire groups and smoke there, and recompute the tag each turn.

### P7. Move by bounds under overwatch; keep every mover covered

- Doctrine: The movement posture escalates with expected contact: travel when contact is unlikely, traveling overwatch when possible, bounding overwatch when expected. In bounding overwatch one element always halts in cover with good fields of fire to watch the other. A bound never goes past where the overwatch can support it by fire; the bound length is capped by cover and the overwatch weapon range.
- Mechanism: A stationary overwatch element scans and fires faster than a moving one, so it can suppress any enemy that engages the mover. A bound that ends in the open or out of overwatch range strands the mover for the enemy fire phase.
- Source: FM 3-90 offense para 2-17 to 2-23, 2-21 to 2-22; web set findings 4 and 5 (ATP 3-21.8, ATP 3-20.15, FM 17-15: bound must not exceed overwatch fire range).
- In the game, the agent should never advance a stack past the fire support of a stationary friendly stack that has line of sight to the mover path, and should end each bound in a hex with a cover modifier that stays inside the overwatch stack's range and line of sight.

### P8. Minimize exposure; cross open ground fast under cover or smoke

- Doctrine: Cross open areas quickly, avoid kill zones and open ground overlooked by higher terrain, and prefer cover and concealment. Where none exists, screen the bound with smoke.
- Mechanism: Each open hex in enemy line of sight is another chance to be fired on. Smoke that blocks or hinders line of sight denies the defender a fire solution without suppressing every shooter.
- Source: FM 3-90 offense para 2-17, 1-118, 5-75, 5-71; web set finding 6 (ATP 3-21.8: use cover and concealment, screen with obscurants); MCDP 1-3 ch.3 (exploiting the environment, PDF p.52 to p.53).
- In the game, the agent should score each candidate path by the count of open hexes in enemy line of sight, pick the minimum-exposure path even at extra movement cost, and lay smoke to block the covering enemy's line of sight to the lane when the only path crosses open ground.

### P9. Infiltrate; use concealment and gaps to reach an unexpected firing position

- Doctrine: Move undetected through gaps and blocked line of sight to reach a flank support-by-fire hex or an assault position, and keep concealment until the decisive moment.
- Mechanism: Concealment counters, dummies, and line-of-sight-blocking terrain let a unit reach an advantageous hex before the defender can bring fire, which banks a first-shot advantage.
- Source: FM 3-90 offense para 2-82 to 2-83, 2-101 to 2-102.
- In the game, the agent should prefer movement paths whose every hex is out of line of sight of all unsuppressed enemy fire groups, keep the concealment counter until it fires, and use dummy stacks to hide the real route.

### P10. Adopt the ambush mentality; hold fire, stay unseen, shock at short range

- Doctrine: Do not engage piecemeal at long range. Stay concealed or hidden, let the enemy commit into the kill zone, then open with every eligible weapon at once at short range for shock.
- Mechanism: Firepower rises sharply as range falls, and many results in one impulse cause simultaneous morale checks the enemy cannot recover from.
- Source: MCDP 1-3 ch.3 (ambush mentality, PDF p.61 to p.65); web set finding 8 (FM 7-10: final protective fire held until the assault); FM 3-90 defense para 8-60, 8-61 (simultaneous fires).
- In the game, the defending agent should hold fire from concealed or hidden positions until enemy units enter the shortest-range best-column hexes, then fire all eligible groups in one fire phase; the weaker or reverse-slope defender always chooses this simultaneous mode over echeloned fire.

### P11. Trap the enemy; block the rout, then break

- Doctrine: Aim to cut off and destroy, not to push. A pushed enemy returns; a trapped enemy loses cohesion. Isolate the objective by fire and blocking positions so the enemy cannot reinforce and a broken unit cannot rout to cover.
- Mechanism: A broken unit routs to cover along the shortest safe path. If the agent covers the rout hexes, the break becomes an elimination or a surrender, not a recoverable rout, and the unit cannot rally.
- Source: MCDP 1-3 ch.3 (trapping, PDF p.59 to p.61); FM 3-90 offense para 5-57 to 5-58, Appendix C (hammer and anvil).
- In the game, before it breaks a target, the agent should position a unit or a fire lane across the target's likely rout hexes and its reinforcement hexes, so the break becomes a loss.

### P12. Break cohesion and will, not raw casualties; kill leaders

- Doctrine: The object is the enemy force and its will to fight, not the ground. Value results that suppress and disorganize (pin, morale check, break) and especially the loss of a leader.
- Mechanism: Pinning and breaking turn off a defender's firepower far more cheaply than eliminating him. A lost leader degrades the morale and rally of every unit that relied on him, and cohesion collapse cascades.
- Source: MCDP 1-3 ch.4 and ch.3 (the moral dimension, PDF p.62, p.61); MCDP 1-3 foreword (PDF p.14).
- In the game, the agent should add a large target-value bonus for a hex that holds a leader or a support weapon that other units depend on, and should prefer fire that suppresses a whole stack over fire that eliminates one lone unit.

### P13. Combined arms: tanks and infantry cover each other

- Doctrine: Infantry screens the tank against hand-held anti-tank weapons in close terrain; the tank main gun and machine gun suppress infantry the foot troops cannot. Lead dismounted against a strong anti-tank presence with the vehicle in overwatch; mount only against weak or disorganized resistance.
- Mechanism: Each arm covers the other's blind spot. A lone vehicle in close terrain is in panzerfaust or bazooka range; infantry in the open needs the vehicle's fire.
- Source: FM 3-90 offense para 5-81 to 5-86, 5-88, 2-25; web set finding 10 (ATP 3-20.15: tanks need close infantry screening, tanks overwatch dismounted movement); MCDP 1-3 ch.6 (cooperating, PDF p.99 to p.101).
- In the game, the agent should keep infantry adjacent to friendly vehicles in buildings and woods, use the vehicle main gun and machine gun as a base of fire and for overrun of suppressed infantry, and never send a vehicle alone into close terrain next to concealed enemy without an infantry escort.

### P14. Fight asymmetrically; strength against weakness

- Doctrine: Do not trade like for like. Pit a strong capability against a weak one and force the fight onto favorable terms; refuse an unfavorable matchup.
- Mechanism: The game is full of asymmetric matchups: hand-held anti-tank and close assault against armor's weak flank or rear or in close terrain, overrun against units in the open, massed fire against a lone unit.
- Source: MCDP 1-3 ch.3 (asymmetry, PDF p.65 to p.66).
- In the game, the agent should compute a matchup advantage for each possible engagement (my capability, enemy capability, terrain) and pursue only the positive ones; it engages armor with anti-tank or close assault in close terrain, and declines to expose infantry in the open to an intact enemy support weapon.

### P15. Screen with smoke and obscuration; blind the enemy at the assault

- Doctrine: Use smoke to break the enemy line of sight to the movers and to cover repositioning, while friendly firing positions still see into the kill zone. Do not place smoke so it blocks the friendly base-of-fire line of sight.
- Mechanism: Smoke blocks or hinders line of sight in the engine. The defender wants smoke between the attacker and its own exposed movers, not between itself and the area it must fire into.
- Source: FM 3-90 offense para 5-75, 5-79; FM 3-90 defense para 8-77, 8-78; MCDP 1-3 ch.3 (PDF p.54).
- In the game, the agent should place smoke in a hex only if it reduces the incoming firepower on a friendly stack (or the enemy line of sight to a repositioning stack) by more than it reduces the friendly firepower into the kill zone.

### P16. Deceive with dummies, concealment, and a feint

- Doctrine: Mislead the enemy about strength, location, and intent so he defends everywhere and is strong nowhere, or commits against a threat that is not real.
- Mechanism: The concealment counters and dummy stacks hide real strength and create fake strength; a human who must guard several thrusts thins his fire and mis-allocates his best units.
- Source: MCDP 1-3 ch.3 (surprise and deception, PDF p.57 to p.59); FM 3-90 defense para 9-42, 19-26, 19-60 to 19-62.
- In the game, the agent should keep at least two apparent threats (one real main effort, one demonstration or dummy), keep real high-firepower stacks concealed until the trigger range, and use smoke to hide the real axis before contact.

### P17. Win tempo; every turn advances the plan or forces a reaction

- Doctrine: Act faster than the enemy can restore his line. Keep the initiative, press a broken or pinned enemy the next turn, and never pass a turn without improving position, firepower, or objective control.
- Mechanism: A defender given a quiet turn rallies broken units, refaces armor, and reoccupies cover. Continuous pressure denies him those recovery actions.
- Source: MCDP 1-3 ch.4 (tempo and the decision cycle, PDF p.62 to p.71); FM 3-90 offense para 3-9 to 3-10, 5-60.
- In the game, the agent should score each candidate turn by objective progress plus the count of enemy units forced into a reactive state, avoid a turn with zero progress and zero suppression, and if an enemy stack broke last turn should keep it broken or eliminate it this turn.

### P18. Once ahead, press harder; exploit the gap and pursue the broken

- Doctrine: When you gain an advantage, increase the pressure, do not ease off. Pour follow-on force through a torn gap into the enemy depth. Pursue a routed enemy to turn a break into destruction.
- Mechanism: A broken unit is fragile: fired on again while broken it can be eliminated, and if its rally fails or its rout is blocked it is lost. A hole opened in the line exposes the flanks and rout routes of the units behind it.
- Source: MCDP 1-3 ch.2 (boldness, PDF p.43 to p.44) and ch.7 (exploitation and pursuit, PDF p.108 to p.112); FM 3-90 offense para 2-46 to 2-47 (penetration widened from inside).
- In the game, when the enemy is disordered the agent should keep firing on shaken units to prevent rally, push the maneuver element into the opened hex the same turn, and advance to keep broken units in range and block their rout instead of turning to a fresh intact target.

### P19. Keep a reserve; commit it to exploit success, not to start the attack

- Doctrine: Hold about 10 to 20 percent of usable combat power uncommitted and central, plan for the likely branches, and commit the reserve to reinforce a breakthrough or seal a crisis. Once committed the reserve becomes the main effort.
- Mechanism: An uncommitted stack near the point of decision lets the agent reinforce whichever hex is breaking, without over-committing on turn one.
- Source: FM 3-90 offense para 1-94 to 1-96, 2-41, 2-56; MCDP 1-3 ch.5 and ch.7 (flexible plans and the reserve, PDF p.94, p.113 to p.116).
- In the game, the agent should keep one stack out of the first fire and assault, positioned centrally, and feed it into a hex only after a break or casualty opens the objective or a friendly flank is threatened, then treat it as the main effort.

### P20. Make contact with the smallest element; bypass what you can

- Doctrine: Contact the enemy with the smallest element, react, develop the situation, then choose attack, bypass, fix, or withdraw. Do not get decisively engaged early. Overrun or bypass a weak off-route enemy rather than trading fire for turns.
- Mechanism: A single scout triggering the enemy reveals the enemy position and firepower at minimum cost and keeps the main body free and concealed. Time spent on a minor enemy is time the objective's defender uses to prepare.
- Source: FM 3-90 offense para 1-69 to 1-83, 4-2, 5-69; web set finding 2 (FM 3-21.8 para 1-168 to 1-169: the engage / support-by-fire / break-contact decision tree keyed to relative strength).
- In the game, on first contact the agent should lead with one expendable or concealed unit to draw first fire and reveal enemy cover, keep the main stacks concealed, and branch by relative firepower: assault if it wins fire superiority with an element to spare, set a base of fire if the whole force is needed to win it, or break contact if it cannot win it.

### P21. Hold and defend an engagement area with interlocking, layered fire

- Doctrine: On defense, choose where to kill, then build everything toward it. Site the kill zone on the approach the attacker must use, cover every approach hex with at least two positions (interlocking fire), and layer the defense in depth so a penetration runs into a second position. Use terrain and obstacles to canalize the enemy into the kill zone, and reserve a support weapon for final protective fire (grazing fire down the approach) at the moment of the assault. Site machine guns to fire down the enemy axis (enfilade) along a long low lane.
- Mechanism: Massed fire on one small area produces break results scattered fire cannot. Two-defender coverage means one broken position does not open a gap. Depth means one penetration does not fail the whole defense. The highest-firepower shot must land when the attacker is closest and most exposed.
- Source: FM 3-90 defense para 8-51, 8-52, 8-66, 8-68, 9-30 to 9-33; web set findings 7 and 8 (FM 3-22.68, ATP 3-21.8: grazing fire, final protective line, enfilade; FM 7-10: final protective fire).
- In the game, the defending agent should name a target hex band on the shortest approach as the kill zone, place every high-firepower unit so its line of sight covers that band with at least two-defender overlap, split the force into a forward line and a depth line, treat slow terrain as free obstacles that funnel the attacker into the kill zone, and hold the reserved machine gun until an attacker enters the adjacent ring, then fire it.

### P22. Counterattack the exposed penetration; spoil the forming attack; stay flexible

- Doctrine: Keep the option to seize the initiative. Counterattack the flank or rear of a penetration when the attacker is stopped, depleted, and disorganized, with the smallest force that can win. Spoil an attacker that is still forming up by striking its exposed leaders and support weapons, then withdraw. Shift the main effort and reposition weapons laterally as the attacker reveals his axis.
- Mechanism: An attacker that just seized a position is disorganized and its flanks are exposed, so a concentrated flank close combat gets the high-odds fight. The attacker is most vulnerable while massed and unready in its assembly hexes. A static plan is beaten once the attacker finds the seam.
- Source: FM 3-90 defense para 8-1, 8-2, 8-5, 9-10 to 9-13, 9-96, 8-58, 9-38, 9-39, 8-94, 8-95, 9-25.
- In the game, the defending agent should hold a leader-led reserve and counterattack a lone or reduced attacker in a just-taken hex from a flank or rear with local superiority; spoil an exposed enemy leader or support weapon with a concealed or mobile stack when it can do so at favorable odds; and each turn shift uncommitted firepower toward the attacker's revealed main axis and move a weapon about to be overrun sideways so it keeps line of sight into the penetration.

## 3. National doctrine profiles

State only what the research supports and flag what is unsupported. German and United States doctrine are well-sourced. Soviet doctrine is partial. British doctrine is unsupported and must not be asserted as a distinct profile.

Corrections that the research confirmed:
- The combined-arms survey commonly cited is House, "Toward Combined Arms Warfare: a Survey of 20th-century Tactics, Doctrine, and Organization" (1984), not "Combined Arms Warfare in the Twentieth Century".
- The claim that the Browning Automatic Rifle was the rifle squad's automatic weapon in the sense of a maneuverable squad fire base was refuted (a 1 to 2 vote against).
- The specific mission-command wording claim (that Auftragstaktik split "what to do" from "how to do it") did not survive the check, but the broader finding stands: German doctrine gave subordinates adaptive intellectual tools for decision at the point of contact rather than a fixed rule set.

### 3.1 German

Well-sourced. The German profile is high command flexibility and initiative, high aggression, and a habit of flanking and counterattack.

- Truppenfuehrung, the basic manual from 1934 to the end of the war, gave commanders adaptive intellectual tools for a changing battle, not a cookbook. Source: Condell and Zabecki, "On the German Art of War: Truppenfuehrung". This supports a high command-flexibility and initiative prior.
- Bewegungskrieg (a war of movement) sought rapid movement, surprise, and flanking to outflank and annihilate the enemy in short decisive operations, in a culture that rewarded aggression. Source: Citino, "The German Way of War". This supports high aggression, a flanking preference, and a counterattack habit.
- Combined-arms and armor cooperation (the Kampfgruppe and Schwerpunkt basis) was built in the interwar Reichswehr under von Seeckt from 1919 to 1933, before the Nazi era. Source: Corum, "The Roots of Blitzkrieg". This supports armor-infantry cooperation as a habit.
- Caveat: the Citino "German way" thesis and the Mansoor thesis below are argued theses from publisher and author summaries, fit for priors, not settled fact.

### 3.2 United States (American)

Well-sourced. The United States profile is high reliance on suppressive fire, a flank preference, and adaptability with lower command fragility.

- FM 7-10 (1944) built the base-of-fire and fire-and-movement method: close by fire and movement using terrain, cover every mover with suppressive fire that neutralizes the enemy able to fire on the movers, and pin the enemy by frontal and flanking fire while others maneuver. Source: FM 7-10 (1944). This supports high suppressive-fire reliance and a flank preference.
- United States effectiveness rested on adaptability and learning, not only on material; United States divisions equalled or beat German ones. Source: Mansoor, "The GI Offensive in Europe". This supports an adaptive prior over pure attrition and lower command fragility (argued thesis).

### 3.3 Soviet

Partial. Only the Pakfront, PTOP (anti-tank strongpoint), reverse-slope, and Kursk items are verified (medium confidence). Do not encode a full Soviet profile beyond the anti-tank and obstacle-integration knobs.

- Verified: dense, centralized anti-tank. The Pakfront put up to ten anti-tank guns under one officer who directed their fire, because dispersed guns were overwhelmed. The Soviets refined this by 1943 into staggered PTOP anti-tank zones tied to mines and obstacles, which blunted the German armor at Kursk. Source: Pakfront (encyclopedia entry), corroborated by a Glantz Combat Studies Institute report on Kursk. This supports a high centralized and dense anti-tank prior with obstacle integration for the Soviet defender (and, on the German side, anti-tank guns handled as concentrated groups).
- Refuted or unverified: the claim that the Pakfront assigned separate targets to all guns for a simultaneous coordinated ambush did not survive (it was refuted; the verified detail is many guns under one officer, not separate-target assignment). Soviet items BUP-42, PU-36, the mass echelon attack, and counter-preparation artillery are unverified here.
- Caveat: casualty tolerance, reconnaissance and security, close-combat, and morale-fragility knobs for the Soviet side are weakly backed and are marked accordingly in Table B.

### 3.4 British

Unsupported. Do not assert a distinct British profile. Every British and Canadian section-firepower and fire-and-movement claim in the research was refuted or unconfirmed:

- The claim that the Bren light machine gun was the primary fire-producing weapon with riflemen as ammunition carriers was refuted.
- The claim that British and Canadian fire-and-movement was organized around alternating sub-group fire and maneuver ("keeping one leg on the ground") was unconfirmed (a 0 to 0 vote, no evidence either way).
- The claim that German sections carried more automatic weapons and that the belt-fed MG34 and MG42 outmatched the magazine-fed Bren in a platoon fire-fight was unconfirmed.

A distinct British profile needs a follow-up research pass with French, "Raising Churchill's Army", and Place, "Military Training in the British Army 1940-1944", before it goes into the game. Until then the British agent uses the universal profile with no national bias, and Table B marks its cells "unsourced".

## 4. Doctrine-breaking idea library

These are transferable unconventional tactics. Each states the game condition under which a departure from doctrine improves the outcome. This seeds an agent that periodically departs from the default heuristic when the departure raises the expected result.

- Reverse-slope surprise. Place the main stacks one hex behind a line-of-sight-blocking crest, hold fire, and let the attacker crest into short range before firing everything at once. Advantageous when the enemy outranges the agent or has off-board artillery or air, because the crest denies observed and long-range fire and forces an infantry-range fight. Source: FM 3-90 defense para 9-101 to 9-113; web set finding 9 (FM 7-10 reverse slope); national finding 6 (CALL 1-88, reverse slope at Wireless Ridge). Condition: the agent holds a hex the enemy cannot see at the start of his move, and the enemy has a range or indirect-fire advantage.
- Infiltration and storm-group shock. Move concealed units through gaps to a flank support-by-fire hex, then open at close range. Advantageous when the enemy line has a seam or unwatched blocked-line-of-sight corridor and the agent has concealment counters or dummies to spend. Source: FM 3-90 offense para 2-82 to 2-83; MCDP 1-3 ch.3 (ambush).
- Feint and flank. Threaten one axis with a demonstration or a dummy stack while the real main effort moves on another. Advantageous when the human must guard more than one approach and has limited high-firepower units to cover them, so the feint draws his defensive fire and reserve to the wrong hex. Source: MCDP 1-3 ch.3 (surprise); FM 3-90 defense para 19-60 to 19-62.
- Unexpected concentration. Mass the whole force against one narrow seam (the boundary between two enemy stacks) instead of an even push. Advantageous when no open flank exists but a low-cover, lightly-covered breach hex is reachable and the reserve can exploit it. Source: FM 3-90 offense para 2-36 to 2-57 (penetration).
- Turning movement. Threaten a rear objective or the enemy's rout path so a defender in high cover must move out to reface, then fire on him in the open. Advantageous when an enemy stack sits in a high-cover hex the agent cannot break by frontal fire, and a credible rear threat exists. Source: FM 3-90 offense para 2-71, 2-80.
- Spoiling attack. Strike an attacker's exposed leaders and support weapons while he is still massed and unready in his assembly hexes, then withdraw. Advantageous early, when the attacker is clustered and a concealed or mobile agent element can reach an exposed leader at favorable odds without committing the main line. Source: FM 3-90 defense para 8-58, 9-38, 9-39.
- Anti-armor flank ambush. Hold hand-held anti-tank in concealment, do not fire it at vehicle front armor, and trigger it only when the vehicle presents flank or rear armor in the kill zone. Advantageous whenever an enemy vehicle's movement will present a weak facing to a still-concealed unit one move away. Source: FM 3-90 defense para 5-104 to 5-112, 8-68.

## 5. Table A: principle to game lever to v4 heuristic to reinforcement learning reward term

One row per principle. The v4 heuristic column is a one-line computable rule against the engine. The reward-term column names a per-step shaping signal, its sign, and a rough magnitude intent (small, medium, large).

| Principle | Game lever | v4 heuristic (computable) | RL reward term |
|-----------|-----------|---------------------------|----------------|
| P1 Suppress before you move | prep fire; morale model | Do not move a stack into a hex an unsuppressed enemy fire group can hit at break odds; if the move is needed, prep-fire that enemy first and re-check its status. | r_suppress_before_move: + medium when a covering enemy is pinned or broken in the same turn before the mover starts. |
| P2 Concentrate fire, no overkill | fire group; IFT columns | target = argmax(P(break) times threat_value); add all units with LOS and range to one group; stop adding once P(break) crosses the threshold, then shift surplus. | r_fire_efficiency: + medium per enemy broken per firepower spent; - small for firepower on an already-broken target. |
| P3 Base of fire and maneuver; dilemma | two-stack split; phases | If a maneuver is planned, assign a fire element large enough to pin the target, fire it, then advance the assault stack; never move the assault into the open before the base of fire has fired. | r_dilemma: + medium when the same target is both suppressed and adjacent to a friendly assault-capable unit in one turn. |
| P4 Flank or rear, not front | flank/rear direction; covered arc | Prefer the assault or close-combat hex on the target flank or rear; for a vehicle, prefer the covered-arc hex that presents flank or rear armor; allow a frontal assault only if P(break) is high. | r_flank: + medium for ending adjacent to an enemy flank or rear; + large for a vehicle shot on flank or rear armor; - small for a low-odds frontal assault. |
| P5 Fix the many, mass the few | local force ratio | At the chosen hex, ensure local attacker firepower and unit count with the leader modifier cross the favorable column; elsewhere spend only enough fire to threaten a check. | r_local_ratio: + medium for local ratio above threshold at the point of assault while other enemy cannot reach it. |
| P6 One main effort per turn | leader, fire group, smoke allocation | main_effort = argmax(objective_value times P(breakthrough)); route the best leader, largest fire groups, and smoke there; recompute each turn. | r_concentration: + small for the fraction of usable firepower on the main-effort sector; - small for idle unbroken units far from any objective. |
| P7 Bounds under overwatch | LOS; weapon range | Never advance a stack past a stationary friendly stack that has LOS to its path and range to any enemy on it; end each bound in a cover hex inside the overwatch range and LOS. | r_overwatch: + small for ending in cover under friendly overwatch; - medium for moving into contact with no friendly LOS and range to suppress the shooter. |
| P8 Minimize exposure; smoke the open | path exposure; smoke | Score each path by the count of open hexes in enemy LOS; pick the minimum; if the only path crosses open ground, smoke the covering enemy's LOS to the lane first. | r_exposure: - small per open enemy-observed hex a unit occupies; + small when smoke removes an enemy LOS to the mover path. |
| P9 Infiltrate through gaps | concealment; LOS gaps | Prefer paths whose every hex is out of LOS of all unsuppressed enemy fire groups; keep the concealment counter until the decisive hex; use dummies to mask the route. | r_infiltrate: + medium for reaching a flank support-by-fire hex with an enemy in LOS while still concealed. |
| P10 Ambush; hold fire, shock at short range | concealment; simultaneous fire | If defending and the target is beyond optimal range with no forcing reason to fire, hold fire and keep concealment; fire all eligible groups when the enemy enters short-range best-column hexes. | r_ambush: + medium for total firepower delivered in one phase at short range; + small for keeping concealment until first fire; - small for low-yield long-range fire. |
| P11 Trap; block the rout | rout path; blocking | rout_hexes = predicted_rout_path(target); if a friendly unit can cover them cheaply, place it there before delivering the breaking fire; also cover reinforcement hexes. | r_trap: + large for eliminating a unit by failure-to-rout or surrender; + medium for covering the only cover-ward rout hex. |
| P12 Break cohesion; kill leaders | target value; morale | target_value(hex) += large bonus if it holds a leader or a support weapon others depend on; prefer suppression across a stack over eliminating one lone unit. | r_cohesion: + large per leader killed or isolated; + small per enemy unit simultaneously pinned or broken; weight morale effects above raw kills. |
| P13 Combined arms; tank and infantry | AFV plus infantry stacking | Keep infantry adjacent to friendly AFVs in close terrain; use the AFV gun and MG as a base of fire and for overrun of suppressed infantry; never move an AFV alone into close terrain next to concealed enemy. | r_combined_arms: - medium for an AFV in close-terrain contact with no infantry escort; + medium for an AFV overrun or gun result on suppressed infantry. |
| P14 Asymmetry; strength vs weakness | matchup by terrain | For each engagement compute matchup_advantage(my_capability, enemy_capability, terrain); pursue positive ones, decline or reposition on negative ones. | r_asymmetry: + medium for engaging armor from flank/rear or in close terrain with AT or close assault; - medium for infantry in the open against an intact support weapon. |
| P15 Smoke and obscuration | smoke placement; LOS | Fire smoke into a hex only if it lowers incoming firepower on a friendly stack (or enemy LOS to a repositioning stack) by more than it lowers friendly firepower into the kill zone. | r_smoke: + small for smoke that lowers enemy LOS to a mover or router; - small for smoke that blocks the friendly kill-zone LOS. |
| P16 Deceive; dummies and feint | concealment tokens; dummies | Keep at least two apparent threats (one real main effort, one demonstration or dummy); keep real high-firepower stacks concealed until the trigger range; smoke the real axis before contact. | r_deceive: + small when enemy defensive fire hits a dummy or a demonstration; + small for reaching the objective axis without being fired on. |
| P17 Tempo; force a reaction | objective progress; enemy state | Score each turn by objective progress plus the count of enemy units forced into a reactive state; avoid a turn with zero progress and zero suppression; keep a just-broken enemy broken this turn. | r_tempo: + small per turn for net progress plus enemy units forced reactive; - small for a turn with no progress and no suppression. |
| P18 Press; exploit and pursue | broken-enemy state; gaps | When the enemy is disordered, keep firing on shaken units to block rally, push the maneuver element into the opened hex the same turn, and keep broken units in range and block their rout. | r_pursue: + medium per broken enemy eliminated within N turns of the break; - small for letting a broken enemy rally when it could be prevented. |
| P19 Reserve; commit to exploit | uncommitted stack | Keep about 10 to 20 percent of combat power uncommitted and central; commit it only after a break or casualty opens the objective or a friendly flank is threatened; then treat it as the main effort. | r_reserve: + medium for committing the reserve into a hex where the defender is already broken; - small for a no-reserve early commit or an uncommitted reserve at game end with an uncontested objective. |
| P20 Smallest element; bypass | scout unit; relative strength | On first contact lead with one expendable or concealed unit; branch by relative firepower: assault if it wins fire superiority with a spare element, set a base of fire if the whole force is needed, break contact if it cannot win it; bypass or overrun weak off-route enemy. | r_contact: + small for revealing an enemy stack with a single lead unit while the main body stays concealed; - small per turn in a firefight with an off-objective enemy that is not blocking the path. |
| P21 Engagement area; interlocking depth | LOS coverage; FPF weapon | Name a target hex band on the shortest approach as the kill zone; place high-firepower units for two-defender LOS overlap over it; split into forward and depth lines; hold the reserved MG until an attacker enters the adjacent ring, then fire it. | r_engagement_area: + medium per attacker unit entering a kill-zone hex under two-or-more defender LOS; + medium for stopping an attacker in the depth line; - small for any approach hex with zero coverage. |
| P22 Counterattack, spoil, stay flexible | reserve; lateral moves | Counterattack a lone or reduced attacker in a just-taken hex from flank/rear with local superiority; spoil an exposed leader or support weapon with a concealed stack at favorable odds; each turn shift uncommitted firepower to the revealed axis and move an about-to-be-overrun weapon sideways with LOS into the penetration. | r_counter: + medium for a counterattack that retakes a hex or eliminates a penetrating stack; + small for breaking an attacker leader or support weapon before it reaches the kill zone; - small for a counterattack at unfavorable odds or a weapon overrun in place when a lateral covered hex was free. |

## 6. Table B: nation to behavioral bias

Rows are the four nations. Columns are agent parameters and reinforcement-learning priors. Each cell is low, medium, or high, or "unsourced" for the British side. Each value ties to the profile in section 3. "weak" marks a value that the research backs only weakly.

| Nation | Aggression | Counterattack propensity | Support / off-board fire / smoke reliance | Close-combat willingness | Command flexibility / initiative | Defensive elasticity | Reconnaissance / security | Casualty tolerance |
|--------|-----------|--------------------------|-------------------------------------------|--------------------------|----------------------------------|----------------------|---------------------------|--------------------|
| German | high (Citino) | high (Citino) | medium (Corum, combined arms) | medium (weak) | high (Condell and Zabecki) | high (weak, mobile-defense habit from Citino) | medium (weak) | medium (weak) |
| Soviet | medium (weak) | medium (weak) | high for anti-tank and obstacles (Pakfront, Glantz Kursk) | medium (weak) | low (weak; centralized anti-tank control, Pakfront) | high on defense via PTOP anti-tank zones (Pakfront, Glantz) | low (weak) | high (weak) |
| American | medium (FM 7-10) | medium (weak) | high (FM 7-10, base of fire and suppressive fire) | medium (weak) | medium to high (Mansoor, adaptability, argued thesis) | medium (weak) | medium (weak) | low to medium (weak) |
| British | unsourced | unsourced | unsourced | unsourced | unsourced | unsourced | unsourced | unsourced |

## 7. Notes for the agent designer

- Sequencing is the top lever. P1, P3, P7, P8, P10, and P21 all say the same thing in the phase order: suppress or obscure in prep or defensive fire, then move, then keep the base of fire firing, then close combat, then advance. An agent that respects this order beats one that moves first.
- Flanking (P4, P5, P22) and concealment (P9, P16) are how a weaker-firepower side wins; they trade tempo and position for the enemy's cover and orientation advantage.
- The reward terms in Table A are dense (per turn) and tied to the fire table and the morale model, so they suit reinforcement-learning shaping. Reward enemy suppression along the maneuver path and favorable local odds; penalize exposed moves and unsupported frontal assaults.
- The national biases in Table B are priors, not hard rules. The learned agent can move away from them; the scripted v4 agent reads them as parameters. Keep the "weak" and "unsourced" marks so a later research pass can replace a weak knob with a sourced one, and so the British side is not given a false profile.

## 8. Source list

- FM 3-90, Tactics, Headquarters, Department of the Army, 01 May 2023 (public United States Government work). Offense and defense digests.
- MCDP 1-3, Tactics, U.S. Marine Corps, 30 July 1997 (public release).
- FM 3-21.8 and ATP 3-21.8, The Infantry Rifle Platoon and Squad (fire and movement, movement techniques, cover and concealment, grazing fire).
- FM 7-10, The Rifle Company (1944 and later editions): base of fire, final protective fire, reverse slope.
- FM 17-15, Tank Platoon (legacy): bound length limited by overwatch fire range.
- FM 3-22.68, Crew-Served Machine Guns (grazing fire, final protective line, enfilade).
- ATP 3-20.15, Tank Platoon (tank and infantry cooperation, stationary overwatch).
- Condell and Zabecki, "On the German Art of War: Truppenfuehrung".
- Citino, "The German Way of War".
- Corum, "The Roots of Blitzkrieg".
- Mansoor, "The GI Offensive in Europe".
- House, "Toward Combined Arms Warfare: a Survey of 20th-century Tactics, Doctrine, and Organization" (1984).
- Pakfront (encyclopedia entry) corroborated by a Glantz Combat Studies Institute report on Kursk.
- CALL 1-88 (reverse-slope defense, Wireless Ridge).
- For the future British pass: French, "Raising Churchill's Army"; Place, "Military Training in the British Army 1940-1944".
</content>
</invoke>
