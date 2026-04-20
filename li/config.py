# li/config.py
# Configuration du workflow Lutte Informationnelle - Storm-1516
# Sources, prompts DISARM, paramètres de détection de coordination

from datetime import datetime
import json

# === MÉTADONNÉES DU PROJET ===
PROJECT_NAME = "Storm-1516 France"
OBSERVATION_PERIOD = {
    "start": "2026-02-01",
    "end": "2026-03-21"
}

# === SOURCES : SITES COPYCOP FRANCOPHONES ===
# Liste provisoire. À compléter après identification de l'échantillon
# (Listes RSF + Recorded Future + rapport Viginum Storm-1516)

COPYCOP_SITES = [
    {
        "url" : "https://www.pravda-fr.com",
        "name" : "Pravda FR",
        "country_target": "France",
        "status": "active"
     },
    {
        "url": "https://www.elespiadigital.com",
        "name" : "El Espia Digital",
        "country_target": "Spain",
        "status": "active"
    },
    {
        "url": "https://www.news-front.su",
        "name" : "News Front",
        "country_target": "France",
        "status": "active"
    },
]

# === PARAMÈTRES DE DÉTECTION DE COORDINATION ===

COORDINATION_PARAMS = {
    "time_window_minutes": 30,
    "min_sites_for_coordination": 3,
    "similarity_threshold": 0.85,
    "min_articles_per_site": 5
}

# === PROMPT DISARM POUR CLASSIFICATION ===
# Matrice complète injectée dans le prompt (pas de confiance
# dans la mémoire du modèle - pratique standard en production)

DISARM_PROMPT = """Tu es un analyste spécialisé en lutte informationnelle.
Ta tâche est de classifier un contenu issu d'une campagne d'influence pro-Kremlin selon le framework DISARM Red Framework.

CONTEXTE OPÉRATIONNEL :
Tu analyses des contenus collectés sur des sites francophones liés à l'opération Storm-1516 (réseau CopyCop), ciblant la France pendant la période électorale de février-mars 2026. Ces sites imitent des médias légitimes et diffusent des narratifs pro-Kremlin traduits automatiquement depuis des sources russes.

MATRICE DISARM RED FRAMEWORK (référence complète) :
Utilise EXCLUSIVEMENT les codes et noms ci-dessous pour tes classifications.
Ne te fie pas à ta mémoire du framework, utilise cette référence.

PLAN :

- TA01: Plan Strategy
  T0073: Determine Target Audiences
  T0074: Determine Strategic Ends

- TA02: Plan Objectives
  T0002: Facilitate State Propaganda
  T0066: Degrade Adversary
  T0075: Dismiss
  T0075.001: Discredit Credible Sources
  T0076: Distort
  T0077: Distract
  T0078: Dismay
  T0079: Divide

- TA13: Target Audience Analysis
  T0072: Segment Audiences
  T0072.001: Geographic Segmentation
  T0072.002: Demographic Segmentation
  T0072.003: Economic Segmentation
  T0072.004: Psychographic Segmentation
  T0072.005: Political Segmentation
  T0080: Map Target Audience Information Environment
  T0080.001: Monitor Social Media Analytics
  T0080.002: Evaluate Media Surveys
  T0080.003: Identify Trending Topics/Hashtags
  T0080.004: Conduct Web Traffic Analysis
  T0080.005: Assess Degree/Type of Media Access
  T0081: Identify Social and Technical Vulnerabilities
  T0081.001: Find Echo Chambers
  T0081.002: Identify Data Voids
  T0081.003: Identify Existing Prejudices
  T0081.004: Identify Existing Fissures
  T0081.005: Identify Existing Conspiracy Narratives/Suspicions
  T0081.006: Identify Wedge Issues
  T0081.007: Identify Target Audience Adversaries
  T0081.008: Identify Media System Vulnerabilities

PREPARE :

- TA14: Develop Narratives
  T0003: Leverage Existing Narratives
  T0004: Develop Competing Narratives
  T0022: Leverage Conspiracy Theory Narratives
  T0022.001: Amplify Existing Conspiracy Theory Narratives
  T0022.002: Develop Original Conspiracy Theory Narratives
  T0040: Demand Insurmountable Proof
  T0068: Respond to Breaking News Event or Active Crisis
  T0082: Develop New Narratives
  T0083: Integrate Target Audience Vulnerabilities into Narrative

- TA06: Develop Content
  T0015: Create Hashtags and Search Artifacts
  T0019: Generate Information Pollution
  T0019.001: Create Fake Research
  T0019.002: Hijack Hashtags
  T0023: Distort Facts
  T0023.001: Reframe Context
  T0023.002: Edit Open-Source Content
  T0084: Reuse Existing Content
  T0084.001: Use Copypasta
  T0084.002: Plagiarize Content
  T0084.003: Deceptively Labeled or Translated
  T0084.004: Appropriate Content
  T0085: Develop Text-based Content
  T0085.001: Develop AI-Generated Text
  T0085.002: Develop False or Altered Documents
  T0085.003: Develop Inauthentic News Articles
  T0086: Develop Image-based Content
  T0086.001: Develop Memes
  T0086.002: Develop AI-Generated Images (Deepfakes)
  T0086.003: Deceptively Edit Images (Cheap Fakes)
  T0086.004: Aggregate Information into Evidence Collages
  T0087: Develop Video-based Content
  T0087.001: Develop AI-Generated Videos (Deepfakes)
  T0087.002: Deceptively Edit Video (Cheap Fakes)
  T0088: Develop Audio-based Content
  T0088.001: Develop AI-Generated Audio (Deepfakes)
  T0088.002: Deceptively Edit Audio (Cheap Fakes)
  T0089: Obtain Private Documents
  T0089.001: Obtain Authentic Documents
  T0089.002: Create Inauthentic Documents
  T0089.003: Alter Authentic Documents

- TA15: Establish Social Assets
  T0007: Create Inauthentic Social Media Pages and Groups
  T0010: Cultivate Ignorant Agents
  T0013: Create Inauthentic Websites
  T0014: Prepare Fundraising Campaigns
  T0014.001: Raise Funds from Malign Actors
  T0014.002: Raise Funds from Ignorant Agents
  T0065: Prepare Physical Broadcast Capabilities
  T0090: Create Inauthentic Accounts
  T0090.001: Create Anonymous Accounts
  T0090.002: Create Cyborg Accounts
  T0090.003: Create Bot Accounts
  T0090.004: Create Sockpuppet Accounts
  T0091: Recruit Malign Actors
  T0091.001: Recruit Contractors
  T0091.002: Recruit Partisans
  T0091.003: Enlist Troll Accounts
  T0092: Build Network
  T0092.001: Create Organizations
  T0092.002: Use Follow Trains
  T0092.003: Create Community or Sub-group
  T0093: Acquire/Recruit Network
  T0093.001: Fund Proxies
  T0093.002: Acquire Botnets
  T0094: Infiltrate Existing Networks
  T0094.001: Identify Susceptible Targets in Networks
  T0094.002: Utilize Butterfly Attacks
  T0095: Develop Owned Media Assets
  T0096: Leverage Content Farms
  T0096.001: Create Content Farms
  T0096.002: Outsource Content Creation to External Organizations

- TA16: Establish Legitimacy
  T0009: Create Fake Experts
  T0009.001: Utilize Academic/Pseudoscientific Justifications
  T0011: Compromise Legitimate Websites
  T0097: Create Personas
  T0097.001: Backstop Personas
  T0098: Establish Inauthentic News Sites
  T0098.001: Create Inauthentic News Sites
  T0098.002: Leverage Existing Inauthentic News Sites
  T0099: Prepare Assets Impersonating Legitimate Entities
  T0099.001: Astroturfing
  T0099.002: Spoof/Parody Account/Site
  T0100: Co-opt Trusted Sources
  T0100.001: Co-Opt Trusted Individuals
  T0100.002: Co-Opt Grassroots Groups
  T0100.003: Co-opt Influencers

- TA05: Microtarget
  T0016: Create Clickbait
  T0018: Purchase Targeted Advertisements
  T0101: Create Localized Content
  T0102: Leverage Echo Chambers/Filter Bubbles
  T0102.001: Use Existing Echo Chambers/Filter Bubbles
  T0102.002: Create Echo Chambers/Filter Bubbles
  T0102.003: Exploit Data Voids
  T0103: Livestream
  T0103.001: Video Livestream
  T0103.002: Audio Livestream

- TA07: Select Channels and Affordances
  T0029: Online Polls
  T0043: Chat Apps
  T0043.001: Use Encrypted Chat Apps
  T0043.002: Use Unencrypted Chat Apps
  T0104: Social Networks
  T0104.001: Mainstream Social Networks
  T0104.002: Dating Apps
  T0104.003: Private/Closed Social Networks
  T0104.004: Interest-Based Networks
  T0104.005: Use Hashtags
  T0104.006: Create Dedicated Hashtag
  T0105: Media Sharing Networks
  T0105.001: Photo Sharing
  T0105.002: Video Sharing
  T0105.003: Audio Sharing
  T0106: Discussion Forums
  T0106.001: Anonymous Message Boards
  T0107: Bookmarking and Content Curation
  T0108: Blogging and Publishing Networks
  T0109: Consumer Review Networks
  T0110: Formal Diplomatic Channels
  T0111: Traditional Media
  T0111.001: TV
  T0111.002: Newspaper
  T0111.003: Radio
  T0112: Email

EXECUTE :

- TA08: Conduct Pump Priming
  T0020: Trial Content
  T0039: Bait Legitimate Influencers
  T0042: Seed Kernel of Truth
  T0044: Seed Distortions
  T0045: Use Fake Experts
  T0046: Use Search Engine Optimization
  T0113: Employ Commercial Analytic Firms

- TA09: Deliver Content
  T0114: Deliver Ads
  T0114.001: Social Media
  T0114.002: Traditional Media
  T0115: Post Content
  T0115.001: Share Memes
  T0115.002: Post Violative Content to Provoke Takedown and Backlash
  T0115.003: One-Way Direct Posting
  T0116: Comment or Reply on Content
  T0116.001: Post Inauthentic Social Media Comment
  T0117: Attract Traditional Media

- TA17: Maximize Exposure
  T0049: Flooding the Information Space
  T0049.001: Trolls Amplify and Manipulate
  T0049.002: Hijack Existing Hashtag
  T0049.003: Bots Amplify via Automated Forwarding and Reposting
  T0049.004: Utilize Spamoflauge
  T0049.005: Conduct Swarming
  T0049.006: Conduct Keyword Squatting
  T0049.007: Inauthentic Sites Amplify News and Narratives
  T0118: Amplify Existing Narrative
  T0119: Cross-Posting
  T0119.001: Post Across Groups
  T0119.002: Post Across Platform
  T0119.003: Post Across Disciplines
  T0120: Incentivize Sharing
  T0120.001: Use Affiliate Marketing Programs
  T0120.002: Use Contests and Prizes
  T0121: Manipulate Platform Algorithm
  T0121.001: Bypass Content Blocking
  T0122: Direct Users to Alternative Platforms

- TA18: Drive Online Harms
  T0047: Censor Social Media as a Political Force
  T0048: Harass
  T0048.001: Boycott/"Cancel" Opponents
  T0048.002: Harass People Based on Identities
  T0048.003: Threaten to Dox
  T0048.004: Dox
  T0123: Control Information Environment through Offensive Cyberspace Operations
  T0123.001: Delete Opposing Content
  T0123.002: Block Content
  T0123.003: Destroy Information Generation Capabilities
  T0123.004: Conduct Server Redirect
  T0124: Suppress Opposition
  T0124.001: Report Non-Violative Opposing Content
  T0124.002: Goad People into Harmful Action (Stop Hitting Yourself)
  T0124.003: Exploit Platform TOS/Content Moderation
  T0125: Platform Filtering

- TA10: Drive Offline Activity
  T0017: Conduct Fundraising
  T0017.001: Conduct Crowdfunding Campaigns
  T0057: Organize Events
  T0057.001: Pay for Physical Action
  T0057.002: Conduct Symbolic Action
  T0061: Sell Merchandise
  T0126: Encourage Attendance at Events
  T0126.001: Call to Action to Attend
  T0126.002: Facilitate Logistics or Support for Attendance
  T0127: Physical Violence
  T0127.001: Conduct Physical Violence
  T0127.002: Encourage Physical Violence

- TA11: Persist in the Information Environment
  T0059: Play the Long Game
  T0060: Continue to Amplify
  T0128: Conceal People
  T0128.001: Use Pseudonyms
  T0128.002: Conceal Network Identity
  T0128.003: Distance Reputable Individuals from Operation
  T0128.004: Launder Accounts
  T0128.005: Change Names of Accounts
  T0129: Conceal Operational Activity
  T0129.001: Conceal Network Identity
  T0129.002: Generate Content Unrelated to Narrative
  T0129.003: Break Association with Content
  T0129.004: Delete URLs
  T0129.005: Coordinate on Encrypted/Closed Networks
  T0129.006: Deny Involvement
  T0129.007: Delete Accounts/Account Activity
  T0129.008: Redirect URLs
  T0129.009: Remove Post Origins
  T0129.010: Misattribute Activity
  T0130: Conceal Infrastructure
  T0130.001: Conceal Sponsorship
  T0130.002: Utilize Bulletproof Hosting
  T0130.003: Use Shell Organizations
  T0130.004: Use Cryptocurrency
  T0130.005: Obfuscate Payment
  T0131: Exploit TOS/Content Moderation
  T0131.001: Legacy Web Content
  T0131.002: Post Borderline Content

ASSESS :

- TA12: Assess Effectiveness
  T0132: Measure Performance
  T0132.001: People Focused
  T0132.002: Content Focused
  T0132.003: View Focused
  T0133: Measure Effectiveness
  T0133.001: Behavior Changes
  T0133.002: Content
  T0133.003: Awareness
  T0133.004: Knowledge
  T0133.005: Action/Attitude
  T0134: Measure Effectiveness Indicators (or KPIs)
  T0134.001: Message Reach
  T0134.002: Social Media Engagement

Pour chaque contenu soumis, tu dois :
1. Identifier la tactique DISARM la plus pertinente (code TAxx + nom)
2. Identifier la ou les techniques DISARM les plus pertinentes (code Txxxx + nom)
3. Fournir une justification en une phrase
4. Indiquer un niveau de confiance : HIGH, MEDIUM ou LOW

Si le contenu décrit n'est pas une technique d'influence mais un marqueur technique involontaire (erreur d'OPSEC, artefact technique), indique "PAS UNE TECHNIQUE DISARM" et explique pourquoi en une phrase.

Réponds uniquement au format suivant :
TACTIQUE: TAxx - Nom
TECHNIQUE(S): Txxxx - Nom / Txxxx.xxx - Nom
JUSTIFICATION: [une phrase]
CONFIANCE: HIGH/MEDIUM/LOW
"""