import json
import sys
sys.path.insert(0, ".")
from core.analyze import call_claude
from core.analyze import batch_call_claude

DISARM_PROMPT = """Tu es un analyste spécialisé en lutte informationnelle. Ta tâche est de classifier un comportement observé dans une opération d'influence selon le framework DISARM Red Framework.

Voici la structure du framework DISARM Red Framework (16 tactiques) :

PLAN :
- TA01: Plan Strategy (T0073 Determine Target Audiences, T0074 Determine Strategic Ends, T0075 Dismiss, T0075.001 Discredit Credible Sources, T0076 Distort)
- TA02: Plan Objectives (T0002 Facilitate State Propaganda, T0066 Degrade Adversary)

PREPARE :
- TA13: Target Audience Analysis (T0072 Segment Audiences, T0072.001 Geographic Segmentation, T0072.002 Demographic Segmentation, T0072.003 Economic Segmentation, T0072.004 Psychographic Segmentation, T0072.005 Political Segmentation)
- TA14: Develop Narratives (T0003 Leverage Existing Narratives, T0004 Develop Competing Narratives, T0022 Leverage Conspiracy Theory Narratives, T0022.001 Amplify Existing Conspiracy Theory Narratives, T0022.002 Develop Original Conspiracy Theory Narratives, T0040 Demand Insurmountable Proof, T0068 Respond to Breaking News Event or Active Crisis, T0082 Develop New Narratives, T0083 Integrate Target Audience Vulnerabilities into Narrative)
- TA06: Develop Content (T0015 Create Hashtags and Search Artifacts, T0019 Generate Information Pollution, T0019.001 Create Fake Research, T0023 Distort Facts, T0084 Reuse Existing Content, T0084.001 Use Copypasta, T0084.002 Plagiarize Content, T0084.003 Deceptively Labeled or Translated, T0084.004 Appropriate Content, T0085 Develop Text-based Content, T0085.001 Develop AI-Generated Text, T0085.002 Develop False or Altered Documents, T0085.003 Develop Inauthentic News Articles, T0086 Develop Image-based Content, T0086.001 Develop Memes, T0086.002 Develop AI-Generated Images Deepfakes, T0087 Develop Video-based Content)
- TA15: Establish Social Assets (T0007 Create Inauthentic Social Media Pages and Groups, T0010 Cultivate Ignorant Agents, T0013 Create Inauthentic Accounts, T0014 Prepare Fundraising Campaigns, T0090 Create Inauthentic Accounts, T0090.001 Create Anonymous Accounts, T0090.002 Create Cyborg Accounts, T0090.003 Create Bot Accounts, T0090.004 Create Sockpuppet Accounts, T0091 Recruit Malign Actors, T0092 Build Network, T0093 Acquire/Recruit Network)
- TA16: Establish Legitimacy (T0009 Create Fake Experts, T0009.001 Utilize Academic/Pseudoscientific Justifications, T0011 Compromise Legitimate Websites, T0097 Create Personas, T0097.001 Backstop Personas, T0098 Establish Inauthentic News Sites, T0098.001 Create Inauthentic News Sites, T0098.002 Leverage Existing Inauthentic News Sites, T0099 Prepare Assets Impersonating Legitimate Entities, T0099.001 Astroturfing, T0099.002 Spoof/Parody Account or Site, T0100 Co-opt Trusted Sources)
- TA05: Microtarget (T0016 Create Clickbait, T0018 Purchase Targeted Advertisements, T0101 Create Localized Content, T0102 Leverage Echo Chambers/Filter Bubbles, T0102.001 Use Existing Echo Chambers/Filter Bubbles, T0102.002 Create Echo Chambers/Filter Bubbles, T0102.003 Exploit Data Voids, T0103 Livestream, T0104 Social Networks)

EXECUTE :
- TA07: Select Channels and Affordances (T0029 Online Polls, T0043 Chat Apps, T0104 Social Networks, T0105 Media Sharing Networks, T0106 Discussion Forums, T0107 Bookmarking and Content Curation, T0108 Blogging and Publishing Networks, T0109 Consumer Review Networks, T0110 Formal Diplomatic Channels, T0111 Traditional Media, T0112 Email)
- TA08: Conduct Pump Priming (T0020 Trial Content, T0039 Bait Legitimate Influencers, T0042 Seed Kernel of Truth, T0044 Seed Distortions, T0045 Use Fake Experts, T0046 Use Content Search Engine Optimization)
- TA09: Deliver Content (T0114 Deliver Ads, T0114.001 Social Media, T0114.002 Traditional Media, T0115 Post Content, T0115.001 Share Memes, T0115.002 Post Violative Content, T0115.003 One-Way Direct Posting, T0116 Comment or Reply on Content, T0116.001 Post Inauthentic Social Media Comment, T0117 Attract Traditional Media, T0118 Amplify Existing Narrative, T0119 Cross-Posting, T0119.001 Post Across Platform, T0119.002 Post Across Disciplines, T0119.003 Post Across Disciplines, T0120 Incentivize Sharing)
- TA17: Maximize Exposure (T0049 Flooding the Information Space, T0049.001 Trolls Amplify and Manipulate, T0049.002 Hijack Existing Hashtag, T0049.003 Bots Amplify via Automated Forwarding and Reposting, T0049.004 Utilize Spamouflage, T0049.005 Conduct Swarming, T0049.006 Conduct Keyword Squatting, T0049.007 Inauthentic Sites Amplify News and Narrative, T0048 Harass, T0048.001 Boycott/Cancel Opponents, T0048.002 Harass People Based on Identities, T0048.003 Threaten to Dox, T0048.004 Dox)
- TA18: Drive Online Harms (T0047 Censor Social Media as a Political Force, T0123 Control Information Environment through Offensive Cyberspace Operations, T0123.001 Delete Opposing Content, T0123.002 Block Content, T0123.003 Destroy Information Capabilities, T0123.004 Exploit Platform TOS/Content Moderation, T0124 Suppress Opposition, T0124.001 Report Non-Violative Opposing Content, T0124.002 Goad People into Harmful Action, T0124.003 Exploit Platform TOS/Content Moderation, T0125 Platform Filtering)
- TA10: Drive Offline Activity (T0017 Conduct Fundraising, T0017.001 Conduct Crowdfunding Campaigns, T0057 Organize Events, T0057.001 Pay for Physical Action, T0057.002 Conduct Symbolic Action, T0126 Encourage Attendance at Events, T0126.001 Call to Action to Attend, T0126.002 Facilitate Logistics or Support for Attendance, T0127 Physical Violence, T0127.001 Conduct Server Redirect, T0127.002 Encourage Physical Violence)
- TA11: Persist in the Information Environment (T0059 Play the Long Game, T0060 Continue to Amplify, T0128 Conceal People, T0128.001 Use Pseudonyms, T0128.002 Conceal Network Identity, T0128.003 Distance Reputable Individuals from Operation, T0128.004 Launder Accounts, T0128.005 Change Names of Accounts, T0129 Conceal Operational Activity, T0129.001 Conceal Network Identity, T0129.002 Generate Content Unrelated to Narrative, T0129.003 Break Association with Content, T0129.004 Delete URLs, T0129.005 Coordinate on Encrypted/Closed Networks, T0129.006 Deny Involvement, T0129.007 Delete Accounts/Account Activity, T0129.008 Redirect URLs, T0129.009 Remove Post Origins, T0129.010 Misattribute Activity, T0130 Conceal Infrastructure, T0130.001 Conceal Sponsorship, T0130.002 Utilize Bulletproof Hosting, T0130.003 Use Shell Organizations, T0130.004 Use Cryptocurrency, T0130.005 Obfuscate Payment, T0131 Exploit TOS/Content Moderation, T0131.001 Legacy Web Content, T0131.002 Post Borderline Content)

ASSESS :
- TA12: Assess Effectiveness (T0132 Measure Performance, T0132.001 People Focused, T0132.002 Content Focused, T0132.003 View Focused, T0133 Measure Effectiveness, T0133.001 Behavior Changes, T0133.002 Content, T0133.003 Awareness, T0133.004 Knowledge, T0133.005 Action/Attitude, T0134 Measure Effectiveness Indicators or KPIs, T0134.001 Message Reach, T0134.002 Social Media Engagement)

Pour chaque comportement soumis, tu dois :
1. Identifier la tactique DISARM la plus pertinente (code TAxx + nom)
2. Identifier la ou les techniques DISARM les plus pertinentes (code Txxxx + nom)
3. Fournir une justification en une phrase
4. Indiquer un niveau de confiance : HIGH, MEDIUM ou LOW

Si le comportement décrit n'est pas une technique d'influence mais un marqueur technique involontaire (erreur d'OPSEC, artefact technique), indique "PAS UNE TECHNIQUE DISARM" et explique pourquoi en une phrase.

Réponds uniquement au format suivant :
TACTIQUE: TAxx - Nom
TECHNIQUE(S): Txxxx - Nom / Txxxx.xxx - Nom
JUSTIFICATION: [une phrase]
CONFIANCE: HIGH/MEDIUM/LOW"""

comportements = [
   "Création de 193 portails d'information avec des noms de domaines imitant des médias locaux (pravda-fr.com, pravda-de.com, lugansk-news.ru, crimea-news.com), tous construits sur la même charte graphique et les mêmes rubriques.",
    "Hébergement de tous les sites sur des serveurs localisés en Russie partageant la même infrastructure (même ASN 49352, même Net ID 178.21.15, même ETag, même favicon hash -200225920).",
    "Aucun contenu original produit : réplication massive de textes issus de chaînes Telegram pro-russes, d'agences de presse russes (TASS, RIA Novosti, Izvestia) et de sites officiels d'institutions russes.",
    "Publication automatisée à un volume extrême : 152 464 articles en moins de 3 mois sur les 5 sites pravda. Jusqu'à 1 734 articles en un jour pour un seul site. Publication quasi-ininterrompue 24h/24 avec un maximum de 9 contenus par heure sur Telegram.",
    "Test de fonctionnement initial : le 24 juin 2023, pravda-de.com publie 1 687 contenus en une journée alors que les autres sites pravda n'ont encore rien publié. Viginum interprète cela comme un test par l'administrateur.",
    "Sélection minutieuse des sources Telegram francophones pro-russes pour pravda-fr.com (20 chaînes identifiées : BrainlessChanel, Vbachir, russiejournal, russosphere, etc.), adaptées par pays.",
    "Traduction automatisée des contenus depuis le russe, avec des erreurs caractéristiques (Catherine Colonna désignée comme Le ministre ou La Colonne, vidéos VK conservant leurs titres en cyrillique).",
    "Optimisation SEO pour les requêtes longue traîne : apparition en tête des résultats Google pour des combinaisons de mots-clés peu concurrentielles (ex : dirigeant syndical palestine vers pravda-fr.com en premier résultat).",
    "Quadrillage informationnel du territoire ukrainien par 41 portails -news.ru ciblant des localités précises (Kherson, Marioupol, Tiraspol), certaines villes stratégiques ayant deux portails. Extension progressive d'est en ouest entre avril et décembre 2022.",
    "Diffusion de narratifs pro-Kremlin présentant positivement l'opération militaire spéciale, dénigrant l'Ukraine et ses dirigeants (présentés comme corrompus, nazis, incompétents), critiquant l'Occident collectif.",
    "Reprise opportuniste de thématiques d'actualité polarisantes (crises au Niger et au Gabon durant l'été 2023, dénigrement de la présence française au Sahel, promotion de la coopération Russie-Afrique).",
    "Insertion de pravda-fr.com comme source dans un article Wikipédia sur l'opération Gardien de la prospérité en mer Rouge (par l'utilisateur @Lataupefr, le 23 décembre 2023).",
    "Présence de la balise ZOV dans le code source HTML des sites -news.ru (référence au symbole utilisé par l'armée russe en Ukraine).",
    "Création de comptes VK et Telegram associés à chaque site, avec publication automatisée sur ces plateformes (engagement quasi nul).",
    "Promotion régulière du FSB dans les contenus des sites ciblant la Russie (centaines voire milliers d'articles).",
    "Amplification par 304 comptes X automatisés affiliés au dispositif RRN/Doppelgänger, partageant 6 URLs de l'écosystème pravda à partir du 12 octobre 2023.",
    "Organisation d'un faux rassemblement de patriotes français pro-russes devant la Tour Eiffel (31 août 2023), filmé, publié sur YouTube (chaîne créée le même jour), relayé par des chaînes Telegram pro-russes, puis repris par pravda-fr.com.",
    "Extension du réseau vers quasi tous les États membres de l'UE + Balkans + Afrique (Centrafrique, Burkina Faso, Niger) + Asie (Japon, Taiwan, Corée) entre le 20 et le 26 mars 2024, portant le total à 224 portails.",
    "TigerWeb (entreprise de développement web basée en Crimée, fondée par Evgueni Chevtchenko) identifiée comme créateur et administrateur technique du réseau. Logo TigerWeb visible dans des archives, email topnewsua7@gmail.com lié à Chevtchenko. Tentative de dissimulation ultérieure de cette implication.",
    "Liens techniques avec le réseau Inforos (considéré par les États-Unis comme administré par le GRU) : caractéristiques techniques similaires, calendrier de création de sites parallèle, partage de contenus liés à Inforos."
]

results = batch_call_claude(comportements, DISARM_PROMPT, delay=2.0)

for i, r in enumerate(results, 1):
    print(f"\n{'='*60}")
    print(f"Comportement {i}: {r['input'][:80]}...")
    print(f"{'='*60}")
    print(r["output"])

with open("resultats_disarm_dual.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)