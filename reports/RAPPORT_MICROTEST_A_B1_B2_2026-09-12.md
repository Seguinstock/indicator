# Rapport détaillé — Microtests S&P 1500 Lots A, B1 et B2

**Projet : Stock Indicator**  
**Date : 12 septembre 2026**  
**Statut : exploration terminée — aucun stress test effectué — aucune modification de la stratégie de production à partir de ce rapport.**

## 1. Résumé simplifié

Les trois lots exploratoires sont maintenant terminés. Le Lot A couvre 4 fenêtres historiques et les Lots B1 et B2 couvrent chacun 2 fenêtres supplémentaires. Les stratégies générales sont donc observées sur 8 fenêtres au total, tandis que les nouvelles variantes RSI 14/21/Delta RSI sont explorées sur les 4 fenêtres B1+B2 seulement.

Le signal le plus intéressant du Lot A est **Momentum Pullback**, particulièrement en **Top 10 autour de 75 séances**. Le meilleur résultat A est `momentum_pullback | 75 | Top10 | fixed` : rendement moyen **+7,421 %**, médiane **+5,311 %**, benchmark **+1,036 %**, excédent **+6,385 points**, indice battu dans **3/4** périodes. Les sorties `armed15_8` et `surge15_6_tech` réduisent un peu la moyenne, mais améliorent fortement la médiane, ce qui est intéressant pour la régularité.

Le Lot B1 a fait ressortir une piste différente : la combinaison **RSI 14 + RSI 21 + Delta RSI 14**, surtout en Top 10 sur 100 séances. Les variantes de sortie dynamique ont donné des excédents très élevés sur les deux fenêtres B1. Comme l'échantillon n'est que de deux périodes, il s'agit d'un indice à valider, pas d'une preuve.

Le Lot B2 est dominé dans son classement global par **Momentum Pullback**. Son meilleur résultat est `momentum_pullback | 100 | Top30 | fixed` : **+10,381 %** en moyenne contre **+3,730 %** pour le benchmark, soit **+6,651 points d'excédent**, avec **2/2** périodes battant l'indice. Plusieurs sorties `surge` et `armed` restent positives, mais la conservation fixe est la meilleure sur ces deux fenêtres.

### Conclusion simplifiée

1. **Momentum Pullback est la piste générale la plus persistante entre A et B2.**
2. **75 à 100 séances semblent nettement plus favorables que les horizons très courts dans cette exploration.**
3. **Les sélections concentrées Top 10/Top 30 sont souvent plus fortes que Top 100**, ce qui suggère qu'un bon classement peut apporter de la valeur — mais cette relation n'est pas uniforme.
4. **RSI 14 + RSI 21 + Delta RSI 14 est une piste expérimentale prometteuse issue de B1**, à juger sur B1+B2 avant intégration.
5. **Aucune formule ne doit encore être intégrée à Defensive ou à l'application.** Il faut d'abord consolider les résultats, corriger les limites méthodologiques et valider sur des périodes non utilisées.

---

## 2. Protocole expérimental

### Univers et périodes

- Univers : **S&P 1500 historique point-in-time**, via `pitindex`.
- Graine déterministe : `20260910`.
- 8 fenêtres exploratoires déterministes au total.
- Lot A : fenêtres 1 à 4.
- Lot B1 : fenêtres 5 à 6.
- Lot B2 : fenêtres 7 à 8.
- Horizons : **10, 20, 30, 50, 75 et 100 séances**.
- Profondeurs de sélection : **Top 10, Top 30, Top 100**.
- Benchmark : tentative S&P 1500 (`^SP1500`), avec repli sur S&P 500 (`^GSPC`) lorsque nécessaire.

### Familles générales testées

| Famille | Idée | Formule de score exploratoire |
|---|---|---|
| Momentum | privilégier tendance et force récente | 45 % tendance + 35 % retour 20 j + 20 % MACD positif |
| Momentum Pullback | tendance positive avec repli/RSI modéré | 40 % tendance + 25 % RSI centré 42 + 20 % MACD autour de -5 + 15 % faible volatilité |
| Breakout | proximité du sommet récent avec volume/tendance | 45 % proximité du plus haut 60 j + 25 % RVOL + 20 % tendance + 10 % MACD positif |
| Mean Reversion | faiblesse/RSI bas avec soutien | 40 % RSI bas + 25 % support + 20 % MACD négatif + 15 % faible volatilité |
| Low Vol Trend | tendance avec faible volatilité | 50 % faible volatilité + 40 % tendance + 10 % RSI centré 45 |
| Acceleration | amélioration RSI/MACD avec tendance | 35 % rebond Delta RSI + 30 % MACD positif + 20 % tendance + 15 % RVOL |
| Relative Strength | force 20 j relative au benchmark | 50 % force relative 20 j + 30 % tendance + 20 % MACD positif |
| Relative Contrarian | faiblesse relative avec qualité défensive | 45 % faiblesse relative + 25 % RSI bas + 20 % faible volatilité + 10 % support |
| Low MACD | contrôle historique | 50 % MACD négatif + 20 % tendance + 15 % RSI centré 33 + 10 % RVOL + 5 % support |
| Defensive | contrôle historique | 40 % tendance + 30 % faible volatilité + 15 % support + 10 % RSI centré 40 + 5 % RVOL |

### Familles RSI ajoutées dans B1/B2

Le RSI 14 et le RSI 21 sont calculés séparément sur les clôtures historiques disponibles au moment de la sélection. `Delta RSI 14` représente l'accélération/récupération du RSI 14.

| Variante | Formule |
|---|---|
| RSI 14 seul | 100 % qualité RSI 14 bas |
| RSI 21 seul | 100 % qualité RSI 21 bas |
| RSI 14 + RSI 21 | 50 % RSI14 + 50 % RSI21 |
| RSI 21 + Delta RSI14 | 65 % RSI21 bas + 35 % accélération Delta RSI14 |
| RSI14 + RSI21 + Delta RSI14 | 35 % RSI14 + 35 % RSI21 + 30 % accélération Delta RSI14 |
| RSI21 bas + RSI14 accélération | 60 % RSI21 bas + 40 % accélération Delta RSI14 |

Qualité RSI bas : `clip((50 - RSI) / 30, 0, 1)`. L'accélération RSI utilise une fonction de rebond de Delta RSI, approximativement nulle vers -2 et pleinement favorable vers +4.

---

## 3. Règles de sortie testées

| Règle | Description |
|---|---|
| `fixed` | conserve jusqu'à l'horizon fixé |
| `trail5` | sortie après recul de 5 % depuis le sommet post-achat |
| `trail8` | sortie après recul de 8 % depuis le sommet post-achat |
| `trail12` | sortie après recul de 12 % depuis le sommet post-achat |
| `armed10_5` | le trailing 5 % ne s'arme qu'après un gain de +10 % |
| `armed15_8` | le trailing 8 % ne s'arme qu'après un gain de +15 % |
| `surge10_5_tech` | après +10 %, sortie sur recul de 5 % + détérioration technique |
| `surge15_6_tech` | après +15 %, sortie sur recul de 6 % + détérioration technique |
| `surge20_8_tech` | après +20 %, sortie sur recul de 8 % + détérioration technique |

La détérioration technique exploratoire est déclenchée si momentum < 0 et RSI < 48, ou si trois clôtures successives sont décroissantes. Ces règles sont causales dans l'intention : elles ne cherchent pas à vendre au sommet exact.

---

## 4. Résultats détaillés — Lot A

Lot A : 4 périodes, 10 familles générales, 6 horizons, Top10/30/100, 9 sorties.

### Principaux résultats A

| Rang | Famille | Horizon | Top | Sortie | Moyenne | Médiane | Benchmark | Excédent | Bat indice |
|---:|---|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | Momentum Pullback | 75 | 10 | fixed | 7,421 % | 5,311 % | 1,036 % | **+6,385 pp** | 3/4 |
| 2 | Relative Contrarian | 75 | 10 | fixed | 7,039 % | 6,800 % | 1,036 % | +6,004 pp | 2/4 |
| 3 | Momentum Pullback | 75 | 10 | armed15_8 | 6,582 % | 7,942 % | 1,036 % | **+5,546 pp** | 3/4 |
| 4 | Relative Contrarian | 75 | 30 | fixed | 6,233 % | 4,413 % | 1,036 % | +5,197 pp | 2/4 |
| 5 | Momentum Pullback | 75 | 10 | surge15_6_tech | 5,978 % | **8,637 %** | 1,036 % | +4,942 pp | 3/4 |
| 6 | Low MACD | 75 | 10 | surge20_8_tech | 5,784 % | 5,647 % | 1,036 % | +4,749 pp | 3/4 |
| 7 | Low MACD | 75 | 100 | fixed | 5,724 % | 4,759 % | 1,036 % | +4,689 pp | 3/4 |
| 8 | Low MACD | 75 | 100 | surge20_8_tech | 5,555 % | 4,789 % | 1,036 % | +4,519 pp | 3/4 |
| 9 | Low MACD | 75 | 30 | surge20_8_tech | 5,524 % | 3,122 % | 1,036 % | +4,488 pp | 3/4 |
| 10 | Low MACD | 75 | 10 | armed15_8 | 5,467 % | 5,013 % | 1,036 % | +4,432 pp | 3/4 |

### Autres observations A importantes

| Famille | Horizon | Top | Sortie | Moyenne | Médiane | Benchmark | Excédent | Bat indice |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Low Vol Trend | 100 | 10 | surge20_8_tech | 7,125 % | 8,534 % | 3,039 % | +4,085 pp | 3/4 |
| Low Vol Trend | 100 | 10 | fixed | 7,097 % | 8,479 % | 3,039 % | +4,058 pp | 3/4 |
| Defensive | 100 | 10 | fixed | 7,073 % | 8,745 % | 3,039 % | +4,034 pp | 3/4 |
| Momentum Pullback | 50 | 10 | armed15_8 | 3,276 % | 1,162 % | -0,740 % | +4,016 pp | 2/4 |
| Momentum Pullback | 75 | 30 | fixed | 5,041 % | 4,354 % | 1,036 % | +4,005 pp | 3/4 |
| Low MACD | 100 | 100 | fixed | 6,550 % | 5,035 % | 3,039 % | +3,511 pp | 3/4 |

**Lecture A :** Momentum Pullback 75 jours Top10 est le signal le plus convaincant. Relative Contrarian a une bonne moyenne mais seulement 2/4 périodes gagnantes face au benchmark. Low MACD réapparaît, mais sa robustesse reste incertaine. Defensive/Low Vol Trend deviennent beaucoup plus intéressants à 100 jours qu'à 50 jours.

---

## 5. Résultats détaillés — Lot B1

Lot B1 : 2 périodes, familles générales + 6 variantes RSI. L'échantillon est trop petit pour conclure seul.

### Pistes RSI B1 les plus importantes

| Famille | Horizon | Top | Sortie | Rendement moyen | Benchmark moyen | Excédent moyen | Bat indice |
|---|---:|---:|---|---:|---:|---:|---:|
| RSI14 + RSI21 + Delta14 | 100 | 10 | surge10_5_tech | **6,215 %** | -1,932 % | **+8,147 pp** | exploratoire 2 périodes |
| RSI14 + RSI21 + Delta14 | 100 | 10 | armed15_8 | 5,184 % | -1,932 % | **+7,116 pp** | **2/2** |
| RSI14 + RSI21 + Delta14 | 100 | 10 | surge15_6_tech | 4,633 % | -1,932 % | +6,565 pp | exploratoire 2 périodes |
| RSI21 bas + RSI14 accélération | 20 | 10 | fixed | 3,958 % | -0,341 % | +4,299 pp | exploratoire 2 périodes |

**Lecture B1 :** le signal combiné RSI14/RSI21/Delta14 est assez fort pour mériter une validation B1+B2. Il ne faut toutefois pas le confondre avec une validation : deux fenêtres peuvent produire un résultat spectaculaire par hasard.

---

## 6. Résultats détaillés — Lot B2

Lot B2 : 2 périodes, mêmes familles générales et RSI que B1. Le classement global B2 est dominé par Momentum Pullback.

### Top résultats B2

| Rang | Famille | Horizon | Top | Sortie | Moyenne | Médiane | Benchmark | Excédent | Bat indice |
|---:|---|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | Momentum Pullback | 100 | 30 | fixed | **10,381 %** | 10,381 % | 3,730 % | **+6,651 pp** | 2/2 |
| 2 | Momentum Pullback | 100 | 30 | surge20_8_tech | 9,928 % | 9,928 % | 3,730 % | +6,198 pp | 2/2 |
| 3 | Momentum Pullback | 100 | 30 | surge10_5_tech | 9,554 % | 9,554 % | 3,730 % | +5,824 pp | 2/2 |
| 4 | Momentum Pullback | 100 | 30 | surge15_6_tech | 9,368 % | 9,368 % | 3,730 % | +5,638 pp | 2/2 |
| 5 | Momentum Pullback | 100 | 10 | fixed | 9,196 % | 9,196 % | 3,730 % | +5,466 pp | 2/2 |
| 6 | Momentum Pullback | 100 | 30 | armed15_8 | 8,678 % | 8,678 % | 3,730 % | +4,948 pp | 2/2 |
| 7 | Momentum Pullback | 100 | 10 | surge20_8_tech | 8,361 % | 8,361 % | 3,730 % | +4,631 pp | 2/2 |
| 8 | Momentum Pullback | 100 | 10 | armed15_8 | 8,162 % | 8,162 % | 3,730 % | +4,432 pp | 2/2 |
| 9 | Momentum Pullback | 100 | 10 | surge10_5_tech | 8,118 % | 8,118 % | 3,730 % | +4,388 pp | 2/2 |
| 10 | Momentum Pullback | 100 | 100 | fixed | 7,864 % | 7,864 % | 3,730 % | +4,134 pp | 2/2 |
| 11 | Momentum Pullback | 100 | 100 | surge20_8_tech | 7,862 % | 7,862 % | 3,730 % | +4,132 pp | 2/2 |
| 12 | Momentum Pullback | 100 | 100 | surge15_6_tech | 7,789 % | 7,789 % | 3,730 % | +4,059 pp | 2/2 |
| 13 | Momentum Pullback | 100 | 10 | surge15_6_tech | 7,706 % | 7,706 % | 3,730 % | +3,976 pp | 2/2 |
| 14 | Momentum Pullback | 100 | 100 | surge10_5_tech | 7,562 % | 7,562 % | 3,730 % | +3,832 pp | 2/2 |
| 15 | Momentum Pullback | 100 | 100 | armed15_8 | 7,452 % | 7,452 % | 3,730 % | +3,722 pp | 2/2 |
| 16 | Momentum Pullback | 100 | 100 | armed10_5 | 7,243 % | 7,243 % | 3,730 % | +3,513 pp | 2/2 |
| 17 | Momentum Pullback | 100 | 30 | armed10_5 | 7,119 % | 7,119 % | 3,730 % | +3,389 pp | 2/2 |
| 18 | Momentum Pullback | 100 | 10 | armed10_5 | 6,957 % | 6,957 % | 3,730 % | +3,227 pp | 2/2 |
| 19 | Momentum Pullback | 100 | 30 | trail12 | 6,934 % | 6,934 % | 3,730 % | +3,204 pp | 2/2 |
| 20 | Momentum Pullback | 100 | 100 | trail12 | 6,776 % | 6,776 % | 3,730 % | +3,046 pp | 2/2 |

**Lecture B2 :** le fait que la même famille occupe tout le haut du classement est remarquable. Cela renforce l'intérêt de Momentum Pullback, mais peut aussi refléter un régime de marché particulièrement favorable dans ces deux fenêtres. Le test suivant devra donc être hors échantillon.

---

## 7. Ce que les trois lots suggèrent ensemble

### A. Horizon de détention

Le signal le plus clair est la supériorité fréquente des horizons **75–100 séances**. A met en avant 75 jours; B2 met très fortement en avant 100 jours. Cela suggère que le mécanisme recherché n'est probablement pas un simple rebond de quelques jours, mais une sélection qui capte une phase de reprise/tendance sur plusieurs mois.

### B. Concentration Top10/Top30

A favorise fortement Momentum Pullback Top10 à 75 jours. B2 favorise Top30 à 100 jours, mais Top10 reste excellent. Top100 demeure positif mais perd de l'excédent. C'est compatible avec l'hypothèse qu'un score de classement contient de l'information, sans prouver encore que Top10 est optimal.

### C. Sorties

Les sorties dynamiques ne gagnent pas systématiquement sur `fixed`. Dans A, `armed15_8` et `surge15_6_tech` améliorent la médiane de Momentum Pullback 75/Top10 mais réduisent la moyenne. Dans B2, `fixed` domine les sorties dynamiques sur Momentum Pullback 100/Top30. Cela suggère qu'une règle de vente doit être évaluée comme un compromis entre rendement moyen, régularité, drawdown et restitution des gains, pas seulement comme un moyen de maximiser le rendement final.

### D. RSI 14 / RSI 21 / Delta RSI

L'idée d'utiliser deux vitesses de RSI est rationnelle : RSI14 réagit plus vite, RSI21 représente un état plus lent, et Delta RSI14 cherche l'accélération. Le résultat B1 indique qu'un titre encore relativement déprimé sur le RSI lent mais dont le RSI rapide accélère peut constituer un signal de retournement intéressant. Il faut maintenant examiner la même famille sur B2 et ensuite sur des fenêtres nouvelles.

### E. Low MACD et Defensive

Low MACD a produit des résultats intéressants dans A, mais son historique montre une sensibilité aux gros gagnants; il ne faut pas en faire le centre de la stratégie. Defensive reste intéressant pour le contrôle du risque et semble mieux fonctionner à horizon 100 jours dans A, mais les lots exploratoires ne justifient pas de modifier la stratégie Defensive actuelle.

---

## 8. Limites méthodologiques importantes

Ces résultats sont **exploratoires**. Avant validation/stress test, plusieurs points du moteur doivent être corrigés ou contrôlés :

1. La borne de date maximale peut laisser certaines fenêtres de 100 séances incomplètes; la validation devra exiger un horizon complet.
2. Les indicateurs utilisés par les sorties dynamiques reconstruisent actuellement une partie de l'historique pré-entrée de façon simplifiée (`[entry]*30 + closes`). Pour une validation rigoureuse, il faut utiliser les vraies clôtures pré-entrée.
3. Une détérioration détectée à la clôture et exécutée à cette même clôture est optimiste. La validation devrait générer le signal à la clôture et exécuter au prochain prix négociable, par exemple l'ouverture suivante.
4. Les trailing stops sont évalués avec une approximation clôture/sommet et non une simulation intrajournalière exacte.
5. Le fichier exploratoire ne fournit pas encore toutes les métriques prévues : MAE/drawdown par transaction, taux de titres gagnants, MFE, giveback et rendement après sortie.
6. `momentum_pullback` est une approximation de pullback fondée sur tendance/RSI/MACD/volatilité; ce n'est pas encore une mesure explicite de recul depuis un sommet récent.
7. `breakout` mesure surtout la proximité du sommet 60 jours plutôt qu'une vraie cassure au-dessus d'un sommet antérieur excluant la séance courante.
8. Le calcul RSI14/RSI21 du wrapper B1/B2 doit être harmonisé avec la convention RSI du scanner avant intégration définitive.
9. B1 et B2 ne contiennent que deux périodes chacun; les chiffres spectaculaires doivent être traités avec prudence.

---

## 9. Plan recommandé avant stress test

**Ne pas lancer le stress test immédiatement.** D'abord :

- fusionner A+B1+B2 au niveau des périodes individuelles plutôt que moyenner les moyennes;
- produire un classement global des familles générales sur 8 périodes;
- produire séparément le classement RSI sur B1+B2 (4 périodes);
- calculer moyenne, médiane, taux de périodes positives, taux de périodes battant le benchmark et dispersion;
- corriger les points méthodologiques ci-dessus;
- retenir seulement quelques variantes réellement robustes;
- valider ces variantes sur des fenêtres historiques non utilisées;
- seulement ensuite lancer le stress test long, notamment S&P 500 historique 2005–2026.

---

## 10. Données sources et reproductibilité

Fichiers de résultats :

- `data/microtest_lot_a.json` — Lot A historique publié au commit `bc7bc0edea4ecf04bb67ee409e297ad1025d227f`.
- `data/microtest_lot_b1.json` — Lot B1 historique publié au commit `0f1c8adc3810ea4913882777063d5e40242514ab`.
- `data/microtest_lot_b2.json` — Lot B2 publié après le run GitHub Actions `34687419622` terminé avec succès.

Code :

- `engine/microtest_explorer.py` — familles générales, fonctions de qualité, sorties et agrégation.
- `engine/microtest_lot.py` — découpage A/B1/B2 et variantes RSI14/RSI21/Delta RSI.
- `.github/workflows/microtest-lot-b1.yml` et `.github/workflows/microtest-lot-b2.yml` — exécution des lots.

Les JSON constituent la **table exhaustive machine-readable de chaque combinaison testée** (famille × horizon × Top N × sortie × période). Ce rapport présente les résultats humains les plus importants sans recopier des milliers de lignes redondantes; pour tout audit, les données brutes restent la source de vérité.

---

## 11. Décision actuelle

**Aucune modification de `Defensive`, du moteur de production ou de `config/parameter_defaults.json` à ce stade.**

Les deux axes à conserver pour la prochaine étape sont :

- **Momentum Pullback, surtout 75–100 séances, Top10/Top30**;
- **RSI14 + RSI21 + Delta RSI14**, à consolider sur B1+B2 puis à valider hors échantillon.

Le prochain livrable doit être une **fusion analytique A+B1+B2** avec métriques globales recalculées à partir des périodes individuelles, avant toute optimisation supplémentaire.