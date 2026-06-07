This directory, /aoe2civbuilder/, is a civilization builder for the PC game Age of Empires 2:Definitive Edition. Krakenmeister's ("KM") civ builder served as inspiration, but it has become stale and unmaintained. For that reason, we are using Python and Genieutils Python port to create a new civilization builder.

Right now, there are two phases:
1. Utilizing KM's generated civilization JSON files to create stable mods for the community to use, and

2. Building out a full UI, utilizing Flask as a web application/app for users to create civilization names, architecture sets, tech trees, unique units, bonuses, and unque techs, and generate a game mod, right from their own computer, so there is no reliance on a third party service.