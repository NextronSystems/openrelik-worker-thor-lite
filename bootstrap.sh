#!/bin/bash
# This small script will bootstrap the new worker code.
echo "Please answer the below question to bootstrap your initial worker code."
echo
echo -n "Workername? "
read workername
echo -n "Your name? "
read yourname
echo -n "Your email address? "
read youremail
echo -n "A short one line description of the worker? "
read onelinedescription

# OS platform detection
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  sed -i "s/TEMPLATEWORKERNAME/$workername/g" pyproject.toml
  sed -i "s/TEMPLATENAME/$yourname/g" pyproject.toml
  sed -i "s/TEMPLATEEMAIL/$youremail/g" pyproject.toml
  sed -i "s/TEMPLATEWORKERNAME/$workername/g" src/tasks.py
  sed -i "s/TEMPLATEDESC/$onelinedescription/g" src/tasks.py
  sed -i "s/TEMPLATEWORKERNAME/$workername/g" README.md
elif [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i "" "s/TEMPLATEWORKERNAME/$workername/g" pyproject.toml
  sed -i "" "s/TEMPLATENAME/$yourname/g" pyproject.toml
  sed -i "" "s/TEMPLATEEMAIL/$youremail/g" pyproject.toml
  sed -i "" "s/TEMPLATEWORKERNAME/$workername/g" src/tasks.py
  sed -i "" "s/TEMPLATEDESC/$onelinedescription/g" src/tasks.py
  sed -i "" "s/TEMPLATEWORKERNAME/$workername/g" README.md
fi
