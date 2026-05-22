# cyberloutre.fr 🦦

Site perso de **Loutre** (Clara Vnk). Portfolio freelance + projets open source.

Hugo + GitHub Pages, custom domain `cyberloutre.fr`.

## Dev local

Prérequis : [Hugo extended](https://gohugo.io/installation/) (testé en 0.161+).

```bash
hugo server -D
# → http://localhost:1313
```

## Build de prod

```bash
hugo --minify --gc
# → public/
```

## Déploiement

À chaque `git push origin main`, le workflow `.github/workflows/deploy.yml` build le site et le publie sur GitHub Pages.

### Setup initial (une fois)

1. **Push le repo** sur GitHub : `git@github.com:ClaraVnk/cyberloutre.git`
2. **Activer GitHub Pages** :
   - Repo Settings → Pages → Source → **GitHub Actions**
3. **DNS** : sur le gestionnaire DNS du domaine `cyberloutre.fr` (Infomaniak ou autre), ajouter ces enregistrements **A** pour l'apex :
   ```
   cyberloutre.fr.   A   185.199.108.153
   cyberloutre.fr.   A   185.199.109.153
   cyberloutre.fr.   A   185.199.110.153
   cyberloutre.fr.   A   185.199.111.153
   ```
   Et un enregistrement **AAAA** pour IPv6 (optionnel mais recommandé) :
   ```
   cyberloutre.fr.   AAAA  2606:50c0:8000::153
   cyberloutre.fr.   AAAA  2606:50c0:8001::153
   cyberloutre.fr.   AAAA  2606:50c0:8002::153
   cyberloutre.fr.   AAAA  2606:50c0:8003::153
   ```
   Pour le sous-domaine `www` (optionnel) :
   ```
   www.cyberloutre.fr.   CNAME   claravnk.github.io.
   ```
4. Dans Settings → Pages, vérifier que **Custom domain** est bien `cyberloutre.fr` (lu depuis le fichier `static/CNAME`), et **activer "Enforce HTTPS"** une fois que le certificat Let's Encrypt est généré (peut prendre ~15 min).

### Sous-domaines existants

`cyberloutre.fr` (apex) → GitHub Pages.

Les sous-domaines hébergés ailleurs continuent à pointer où ils sont (Infomaniak pour `medicalement-geek.cyberloutre.fr` etc.). **À NE PAS toucher** : seul l'apex bascule sur GitHub Pages.

## Structure

```
.
├── hugo.yaml              # config Hugo
├── layouts/
│   ├── _default/baseof.html
│   └── index.html         # toute la page d'accueil
├── assets/css/main.css    # CSS unique
├── static/
│   ├── CNAME              # custom domain pour GH Pages
│   └── img/
│       ├── loutre.svg     # mascotte
│       └── favicon.svg
└── .github/workflows/deploy.yml
```

## Licence

MIT.
