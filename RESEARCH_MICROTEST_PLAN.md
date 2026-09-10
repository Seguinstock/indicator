# Phase exploratoire — microtests achat + vente

Objectif: découvrir où se trouve réellement le signal avant d'optimiser une stratégie particulière. Aucun stress test longue période à cette étape.

## Univers
- S&P 1500 historique point-in-time.
- Les décisions au jour J utilisent uniquement l'information disponible au jour J.
- Comparaison systématique au S&P 1500 sur exactement la même fenêtre.

## Horizons exploratoires
10, 20, 30, 50, 75 et 100 jours.

## Tailles de portefeuille
Top 10, Top 30 et Top 100.

## Familles d'achat à explorer
1. Momentum pur — tendance forte, force récente, MACD positif.
2. Momentum + repli — tendance longue positive avec correction récente.
3. Breakout — proximité/sortie de sommet récent et participation du volume.
4. Mean reversion — faiblesse récente marquée et RSI bas.
5. Low volatility trend — faible volatilité et tendance régulière.
6. Accélération — amélioration du momentum plutôt que niveau absolu.
7. Force relative — surperformance du titre face au marché.
8. Contrarian relatif — tendance longue viable mais sous-performance récente.
9. Low MACD — conservé comme contrôle, pas comme hypothèse privilégiée.
10. Defensive — conservé comme contrôle de risque.

## Règles de sortie
A. Horizon fixe — contrôle: conserver jusqu'à la fin de la fenêtre.
B. Trailing simple — sortie sur recul depuis le meilleur cours observé après l'achat.
C. Trailing armé — le trailing n'est activé qu'après une hausse minimale depuis l'achat.
D. Détérioration technique — sortie lorsque plusieurs signaux disponibles ce jour-là confirment une dégradation.
E. Envolée + détérioration — laisser courir le titre, puis sortir seulement après une hausse significative suivie d'un recul et d'une confirmation technique.

La sortie ne doit jamais utiliser le futur pour identifier rétrospectivement un sommet.

## Variantes initiales de vente à comparer
- Trailing 5 %, 8 % et 12 %.
- Trailing 5/8 % activé après +10 % ou +15 % depuis l'achat.
- Envolée +10 % puis recul 5 % + détérioration momentum.
- Envolée +15 % puis recul 6 % + détérioration momentum.
- Envolée +20 % puis recul 8 % + détérioration momentum.

## Mesures
Pour chaque combinaison achat / horizon / sortie / Top N:
- rendement moyen et médian;
- excès moyen et médian face au S&P 1500;
- fréquence de surperformance du benchmark;
- taux de positions gagnantes;
- drawdown;
- durée moyenne de détention;
- meilleur gain atteint avant sortie;
- gain abandonné entre le sommet observé et la sortie;
- rendement du titre après la sortie jusqu'à la fin de la fenêtre, afin de détecter les ventes trop précoces.

## Méthode anti-surapprentissage
Étape 1: microtests exploratoires sur un petit ensemble de périodes.
Étape 2: éliminer les familles clairement faibles.
Étape 3: valider les familles prometteuses sur des périodes non utilisées pour leur sélection.
Étape 4: seulement ensuite raffiner les paramètres des meilleures stratégies.
Étape 5: stress test historique séparé après validation.

Critère de succès recherché: une stratégie doit montrer une surperformance répétable du benchmark, et idéalement un gradient Top10 > Top30 > Top100 > benchmark, plutôt qu'un rendement moyen élevé provenant de quelques coups exceptionnels.
