// Aide de MoneyThistle en français (Canada). Traduite par IA; pas encore vérifiée par une personne de langue maternelle.
"use strict";
I18N.helpText({
  guides: {
    about: { title: "À propos de MoneyThistle", body: `
      <p><b>Pourquoi il existe.</b> Pendant des années, Microsoft Money Plus Sunset a été le dernier d'une bonne chose : un logiciel
      de finances gratuit et hors ligne qui gardait tout sur votre propre ordinateur. Microsoft a cessé de faire Money il y a
      longtemps, et l'édition Sunset ne fait que vieillir. MoneyThistle est né du souhait d'une famille de garder cette façon de
      faire, en plus simple : les mêmes comptes, registres, factures, budget et rapports, qui tournent à la maison (sur un
      ordinateur, un serveur domestique ou dans Docker), ouverts dans n'importe quel navigateur sur les ordinateurs et téléphones
      de la famille, sans connexion aux banques, et avec des sauvegardes automatiques vers Nextcloud ou ailleurs. Il est fait pour
      que tout le monde dans la famille puisse l'utiliser, pas seulement la personne qui l'a installé.</p>
      <p>Il a été construit après avoir étudié le comportement de Money Plus Sunset (ses catégories, types de comptes, calendriers
      de factures et règles de sauvegarde), puis écrit de zéro; il ne contient aucun code de Microsoft.</p>
      <p><b>Comment il a été fait : « vibe coding ».</b> Pour être clair dès le départ : MoneyThistle a été écrit par une IA.
      Presque tout son code, ses écrans, cette Aide et ses tests automatisés ont été produits par Claude, d'Anthropic, à partir de
      demandes en langage courant. Son responsable humain a décidé ce qu'il devait faire et comment il devait se sentir, a utilisé
      et testé chaque fonction, a signalé ce qui n'allait pas et a redemandé jusqu'à ce que ça marche. Le responsable n'a pas revu
      le code ligne par ligne.</p>
      <p><b>Ce que ça veut dire pour vous.</b> MoneyThistle a une série de tests automatisés et un vrai usage quotidien derrière
      lui, mais aucune revue de code professionnelle ni audit de sécurité. Donc :</p>
      <ul>
        <li>Gardez des sauvegardes (MoneyThistle les fait tout seul; vérifiez de temps en temps qu'elles sont vérifiées).</li>
        <li>Gardez-le sur votre réseau domestique ou Tailscale, jamais ouvert à l'Internet public.</li>
        <li>Comparez les chiffres importants avec vos relevés bancaires et de carte, comme avec n'importe quel logiciel de finances.</li>
        <li>Si vous savez lire du code : les revues, rapports de bogues et correctifs sont les bienvenus.</li>
      </ul>
      <p><b>Logiciel libre.</b> MoneyThistle est libre et à code source ouvert sous la GNU AGPL-3.0, et il vient sans aucune
      garantie. Vous pouvez l'utiliser, le modifier et le partager; une version modifiée que vous offrez à d'autres, aussi comme
      site Web, doit partager ses changements. Le lien en bas de chaque page télécharge le code source exact de cette copie. Il ne
      prend aucune donnée de vous et n'envoie rien nulle part, sauf là où vous le lui dites (vos sauvegardes et notifications).</p>` },
    start: { title: "Pour commencer", body: `
      <p>MoneyThistle garde l'argent de votre ménage en un seul endroit : les comptes et leurs registres, les factures et dépôts
      dans un calendrier, un budget mensuel, des rapports et des sauvegardes automatiques. Il n'y a pas de connexion à la banque :
      vous tapez les écritures, ou les importez d'un fichier que votre banque vous laisse télécharger.</p>
      <ol>
        <li><b>Ajoutez vos comptes</b> (Comptes → Nouveau) : chèques, épargne, cartes de crédit, prêts, placements.
          Entrez le solde de chacun à une date et, pour les cartes et les prêts, ce que vous devez.</li>
        <li><b>Mettez les factures et paies régulières au calendrier</b> (Factures et dépôts) pour que l'accueil montre ce qui
          s'en vient et que le budget sache à quoi s'attendre.</li>
        <li><b>Inscrivez ce qui se passe</b> dans le registre de chaque compte, ou avec l'<a href="#/help/quick">Ajout rapide</a>
          sur votre téléphone.</li>
        <li><b>Activez les sauvegardes</b> (Sauvegardes) : un dossier et, idéalement, Nextcloud ou un autre serveur WebDAV aussi.</li>
      </ol>
      <p>Personnalisez l'accueil avec <b>Personnaliser</b> sur la page d'accueil. Refaites la visite quand vous voulez à partir de cette page d'aide.</p>` },
    register: { title: "Les comptes et le registre", body: `
      <p>Chaque compte a un <b>registre</b> : chaque écriture avec sa date, son bénéficiaire, sa catégorie, son montant et le solde
      courant. Tapez-en une nouvelle sur la ligne du bas : choisissez <b>Retrait</b> ou <b>Dépôt</b>, puis le bénéficiaire;
      MoneyThistle se souvient de la catégorie et du montant habituels de chaque bénéficiaire.</p>
      <ul>
        <li><b>Modifier une écriture :</b> cliquez-la dans le registre. Elle s'affiche sur la ligne du bas, verrouillée; choisissez
          <b>Modifier l'opération</b>, changez-la, puis <b>Enregistrer les changements</b> (ou <b>Annuler</b>). La poubelle la supprime.</li>
        <li><b>Transferts :</b> comme catégorie, choisissez « Transfert vers … » un autre compte. L'écriture correspondante est
          ajoutée toute seule à l'autre compte.</li>
        <li><b>Écritures ventilées</b> (un paiement de prêt, un talon de paie) s'affichent comme une ligne avec leurs parties dessous.</li>
        <li><b>Ordre :</b> « Plus récentes d'abord » inverse l'ordre. Les écritures d'une même journée se déplacent avec ▲ ▼.</li>
        <li><b>Compensé et rapproché :</b> cliquez la colonne d'état pour marquer une écriture compensée (C) ou rapprochée (R).
          <b>Concilier le compte</b> vous guide pour faire correspondre un relevé.</li>
        <li><b>Détails du compte</b> gardent la banque, le numéro de compte, le site Web, le téléphone et le taux d'intérêt et, pour
          les cartes, la limite et les jours du relevé.</li>
      </ul>` },
    cards: { title: "Cartes de crédit", body: `
      <p>Chaque carte est tenue de l'une de deux façons (Détails du compte → <i>Comment tenez-vous cette carte?</i>) :</p>
      <ul>
        <li><b>Solde du relevé :</b> une fois par mois, vous entrez le solde du relevé; une écriture amène la carte à ce qu'elle
          doit. Avec le jour de fermeture rempli, l'accueil vous rappelle quand un relevé a fermé.</li>
        <li><b>Chaque achat :</b> vous inscrivez chaque achat. Le budget par éléments prévus montre les achats du mois en attente,
          payés plus tard par le paiement de la carte, pour que rien ne compte deux fois.</li>
      </ul>
      <p><b>Payer une carte :</b> un transfert du compte chèques vers la carte. Un bouton propose le solde du dernier relevé (moins
      ce qui a été payé depuis). Cochez <i>Garder le paiement de la carte dans mon calendrier</i> pour avoir le paiement dans
      Factures et dépôts chaque mois le jour d'échéance.</p>
      <p><b>Une carte pour un seul type de dépense</b> (soins admissibles HSA, dons, une entreprise) : choisissez-le sous
      <i>À quoi sert cette carte?</i>. Ses achats et relevés vont alors tout seuls dans cette catégorie.</p>
      <p><b>Dernier jour du mois :</b> entrez 31 comme jour de fermeture ou d'échéance. Les mois plus courts utilisent leur
      dernier jour; 29 et 30 fonctionnent de la même façon en février.</p>` },
    receipts: { title: "Reçus et autres fichiers", body: `
      <p>Gardez une photo du reçu, ou un PDF (une facture, une garantie, une facture médicale pour votre HSA), avec l'écriture à
      laquelle il appartient.</p>
      <ul>
        <li><b>Sur un téléphone :</b> sous une nouvelle écriture, <b>📷 Prendre une photo</b> ouvre l'appareil photo; la photo est
          jointe quand vous appuyez sur Inscrire. <b>Choisir une photo ou un fichier</b> en prend un que vous avez déjà.</li>
        <li><b>Plus tard :</b> choisissez l'écriture dans le registre puis <b>Reçus</b> pour en ajouter, les ouvrir, les
          télécharger ou les retirer. Les écritures avec quelque chose de joint montrent un trombone.</li>
        <li><b>Papiers gardés avec un compte :</b> sur une carte où vous n'inscrivez que les relevés et paiements, il n'y a pas
          d'écriture pour la télé que vous avez achetée. Choisissez <b>Papiers</b> sur la page du compte pour garder le reçu, la
          garantie ou le contrat avec le compte lui-même, avec sa date.</li>
        <li><b>Notes et mots-clés :</b> donnez à tout fichier une courte note (« Télé, garantie 2 ans, série 12345 ») en l'ajoutant,
          ou plus tard sous lui. Tout ce que vous tapez est enregistré quand vous quittez la case.</li>
        <li><b>Fichiers</b> (dans le menu) liste chaque reçu et papier de cet environnement, les plus récents d'abord. Cherchez avec
          n'importe quels mots de la note, du nom de fichier, du bénéficiaire ou du compte; limitez à un compte ou une période;
          cliquez une colonne pour trier.</li>
        <li>Les photos sont réduites avant l'envoi (environ 400 Ko au lieu de plusieurs Mo); un PDF peut faire jusqu'à 20 Mo.</li>
        <li>Les fichiers sont gardés dans le dossier de données et vont dans chaque sauvegarde, y compris Nextcloud.</li>
        <li>Supprimer une écriture met ses fichiers de côté pendant 60 jours, donc annuler la suppression (Historique) les ramène.</li>
      </ul>` },
    paystubs: { title: "Paies et talons de paie", body: `
      <p>Inscrivez une paie avec ce que vous savez. Le <b>salaire net</b> (ce qui est arrivé à la banque) suffit; le salaire brut
      et les retenues du talon peuvent venir maintenant ou plus tard. Dans le compte où arrive la paie, choisissez
      <b>Talon de paie…</b> au-dessus de la ligne d'inscription. Seul le salaire net est requis.</p>
      <ul>
        <li><b>Autres retenues :</b> une fois le salaire brut ajouté, ce qui n'est pas détaillé (brut moins net moins les retenues
          tapées) est affiché et enregistré comme <b>Autres retenues</b>. Détaillez autant ou aussi peu que vous voulez; à 0 tout
          est détaillé. Si les retenues dépassent le brut moins le net, le talon ne peut pas être enregistré avant que les montants
          concordent.</li>
        <li><b>Ajouté après impôts :</b> de l'argent dans le salaire net qui n'est pas de la paie (un remboursement de dépenses, un
          remboursement). Ajoutez-le sous <b>+ Quelque chose ajouté après impôts</b> pour qu'il ne cache pas une retenue.</li>
        <li><b>Paies planifiées :</b> dans Factures et dépôts, cochez <b>C'est une paie</b> sur le dépôt (son montant est le salaire
          net, ou sa moyenne). À l'échéance, <b>Inscrire</b> propose <b>Inscrire seulement le salaire net</b> ou
          <b>Remplir le talon de paie</b>.</li>
        <li><b>Ajouter les détails plus tard :</b> une paie inscrite avec seulement son salaire net est marquée <b>Paie</b> dans le
          registre; ouvrez-la et choisissez <b>Ajouter les détails du talon de paie</b>.</li>
        <li><b>Ce qui manque est signalé :</b> MoneyThistle apprend ce qui est habituel pour chaque employeur (net seulement, brut et
          net, ou chaque impôt et retenue) à partir de ses dernières paies. Une paie avec moins que d'habitude affiche <b>⚑</b> dans
          le registre (<i>salaire brut manquant</i>, <i>manquant : Medicare</i>, ou <i>220,00 $ non détaillés</i> quand les talons
          de cet employeur sont habituellement tout détaillés), et le rapport fiscal de fin d'année les liste sous
          <b>Paies à vérifier</b>. Si brut et net est votre habitude, les Autres retenues ne sont jamais signalées; si net seulement
          est votre habitude, rien ne l'est. <b>Complet tel quel</b> arrête le signalement pour une paie qui n'aura pas plus de détails.</li>
        <li>Chaque impôt ou retenue va dans une catégorie (Impôt fédéral sur le revenu, Assurances : Santé…) ou dans un de vos
          comptes (un REER/401(k), un HSA), où il apparaît comme argent qui entre. Vous ne suivez pas ce compte dans MoneyThistle? Utilisez plutôt
          <b>Épargne et placements</b> (Régime de retraite, Compte santé). Chaque nouveau talon commence comme une copie du
          dernier; déplacez les lignes avec ▲ ▼ (ou Alt+↑ ↓) pour suivre l'ordre de votre talon.</li>
        <li><b>Paie versée dans plus d'un compte</b> (250 $ dans l'épargne, 3 210,14 $ dans le chèques) : sous <i>Déposé dans</i>,
          choisissez <i>+ Ajouter un compte</i> et entrez ce qui est arrivé dans chacun. La paie nette est leur total. Fonctionne
          aussi avec la paie nette seule. Le montant d'une paie planifiée peut être le total ou ce qui arrive dans son propre compte. Un dépôt planifié peut aussi avoir plusieurs comptes (Factures et dépôts, <i>+ Ajouter un compte</i>), chacun avec un
          montant fixe ou la moyenne de ce qu'il a reçu avant; ils sont enregistrés ensemble.</li>
        <li>Dans le budget, une paie compte à son salaire net. Les rapports montrent chaque ligne, et le rapport fiscal de fin
          d'année montre le brut vs le net de chaque employeur.</li>
      </ul>` },
    bills: { title: "Factures et dépôts (le calendrier)", body: `
      <p>Tout ce qui se répète : factures, paies, transferts vers l'épargne, paiements de prêt et de carte. Chaque élément a un
      compte, un montant et une fréquence, de quotidienne à annuelle (ou une seule fois). Un élément mensuel peut tomber le
      <b>dernier jour du mois</b>.</p>
      <ul>
        <li><b>Inscrire</b> inscrit le prochain dans le registre (vous pouvez d'abord changer le montant et la date);
          <b>Sauter</b> passe un élément qui n'a pas eu lieu. Un reçu, relevé ou talon de paie peut l'accompagner : choisissez
          <b>Ajouter un reçu ou un fichier</b> (ou <b>Prendre une photo</b> sur un téléphone) avant d'inscrire.</li>
        <li><b>Montant variable :</b> le calendrier prévoit la moyenne des derniers inscrits.</li>
        <li><b>Automatique ⟳ :</b> marquez les éléments qui se font tout seuls (paiement automatique, dépôt direct). Choisissez
          <i>l'inscrire pour moi</i> et MoneyThistle inscrit chacun à sa date, marqué ⟳ dans le registre.</li>
        <li>L'accueil liste ce qui est bientôt dû; Rapports → Prévisions utilise le calendrier pour prévoir les soldes.</li>
      </ul>
      <p>Couleurs et symboles : l'argent qui entre est vert <b>+</b>, l'argent qui sort est orange <b>−</b>, les déplacements entre
      vos propres comptes sont bleus <b>⇄</b>.</p>` },
    budget: { title: "Le budget", body: `
      <p>Deux styles; changez avec les boutons en haut de la page Budget :</p>
      <ul>
        <li><b>Par catégorie :</b> chaque catégorie du budget reçoit un montant mensuel. Laissez-en une à 0 et elle prévoit ce que
          votre calendrier contient pour elle ce mois-là. Les dépenses s'affichent sur chaque ligne au fur et à mesure.</li>
        <li><b>Par éléments prévus :</b> pour ceux qui ne suivent pas de catégories. Chaque facture, dépôt et transfert du
          calendrier est une ligne : ce qui est prévu ce mois-ci et ce qui a été inscrit.</li>
      </ul>
      <p>Les paiements de prêt comptent en entier (capital, intérêts et entiercement ensemble). Les talons de paie comptent à leur
      salaire net. Quelque chose inscrit d'avance avec la date du mois prochain compte le mois prochain; le budget le signale.</p>` },
    reports: { title: "Rapports", body: `
      <ul>
        <li><b>Où va / d'où vient l'argent :</b> totaux par catégorie pour une période. Cliquez-en une pour voir ses écritures.</li>
        <li><b>Revenus et dépenses :</b> mois par mois pour la dernière année.</li>
        <li><b>Valeur nette dans le temps :</b> tout ce que vous avez moins tout ce que vous devez, mois par mois.</li>
        <li><b>Prévisions :</b> le solde de chaque compte jour par jour à partir d'aujourd'hui, selon votre calendrier. Cochez des
          comptes pour les tracer; cliquez un élément prévu pour marquer son jour.</li>
        <li><b>Impôts :</b> voir <a href="#/help/taxes">le rapport fiscal de fin d'année</a>.</li>
      </ul>
      <p>Les comptes partagés avec cet environnement sont inclus.</p>` },
    taxes: { title: "Le rapport fiscal de fin d'année", body: `
      <p>Rapports → <b>Impôts</b> rassemble tout ce qui est dans les catégories marquées <b>Lié aux impôts</b> (à définir sous
      Catégories) pour une année civile, chaque écriture listée : revenus, puis déductions et dépenses. Téléchargez-le comme tableur
      ou imprimez-le (ou enregistrez-le en PDF) pour votre préparateur.</p>
      <ul>
        <li><b>Paie :</b> avec des talons inscrits, le brut vs le net de chaque employeur et chaque impôt et retenue.
          Pas de W-2 à saisir : comparez ces totaux avec le W-2 que votre employeur envoie.</li>
        <li><b>Comptes d'épargne-santé (HSA) :</b> marquez un compte comme HSA dans ses détails et indiquez qui y verse de l'argent.
          Le rapport additionne vos cotisations après impôts (déductibles) et avant impôts (employeur ou paie, sur votre W-2) dans
          <i>tous</i> vos HSA, les compare au plafond annuel que vous entrez et liste les retraits. Vos propres cotisations faites
          du 1er janvier au 15 avril peuvent compter pour l'année précédente.</li>
        <li><b>Autres devises :</b> le rapport reste dans la devise principale; les comptes dans d'autres devises sont listés pour
          que vous ajoutiez ces montants aux taux de change officiels.</li>
      </ul>
      <p>C'est un sommaire à comparer à vos formulaires fiscaux, pas un conseil fiscal.</p>` },
    import: { title: "Importer de votre banque", body: `
      <p>Dans le registre d'un compte, choisissez <b>Importer un fichier</b> et un fichier téléchargé du site de votre banque :
      <b>OFX, QFX ou QBO</b> (le mieux : ils portent les identifiants de la banque), <b>CSV</b> (un tableur avec des colonnes Date
      et Montant, ou Débit/Crédit) ou <b>QIF</b>.</p>
      <p>Avant que rien soit ajouté, vous voyez une révision : les écritures qui correspondent à une que vous avez déjà (même
      montant à quelques jours près) sont associées au lieu d'être ajoutées deux fois; les doublons exacts sont sautés; vous
      décidez du reste. Importer deux fois le même fichier OFX n'ajoute rien.</p>` },
    "move-in": { title: "Emménager depuis un autre programme", body: `
      <p>Paramètres → <b>Tout importer d'un autre programme…</b> importe chaque compte et son historique d'un coup.</p>
      <ul>
        <li><b>Microsoft Money :</b> Fichier → Exporter, une fois par compte (Loose QIF convient). Choisissez tous les fichiers
          ensemble; chaque compte prend son vrai nom de son solde d'ouverture, et les transferts entre eux se jumellent.</li>
        <li><b>Quicken, Moneydance, KMyMoney, HomeBank, Money Manager Ex, Banktivity :</b> exportez tout dans un fichier QIF.</li>
        <li><b>YNAB, GnuCash, Actual Budget, Mint, Firefly III :</b> leur exportation CSV de toutes les opérations. Tout autre CSV
          fonctionne s'il a des colonnes Compte, Date, Bénéficiaire, Catégorie et Montant.</li>
      </ul>
      <p>Vous voyez d'abord ce que contient le fichier : chaque compte avec ses écritures, dates et solde, et les catégories qu'il
      ajouterait. Pour chaque compte, choisissez un nouveau compte, un que vous avez déjà, ou le laisser de côté. Rien ne change
      avant <b>L'importer</b>.</p>
      <p>Ce qui vient : comptes, soldes d'ouverture, catégories, bénéficiaires et chaque opération avec ses ventilations, transferts
      et marques de compensation. Ce qui ne vient pas : factures prévues, budgets et placements détenus. Les écritures déjà dans un
      compte choisi ne sont pas ajoutées deux fois. Faites une sauvegarde d'abord; le téléchargement bancaire d'un seul compte
      passe toujours par <a href="#/help/import">Importer un fichier</a>.</p>` },
    history: { title: "Historique des changements et annulation", body: `
      <p>MoneyThistle note chaque écriture, élément prévu, compte, catégorie et montant de budget ajouté, modifié ou supprimé : qui
      l'a fait, quand, dans quel environnement, et comment c'était avant et après. C'est gardé un an et fait partie de chaque sauvegarde.</p>
      <ul>
        <li><b>Tout :</b> Personnes → <b>Historique des changements</b> (ou Paramètres → Vos données). Filtrez par environnement ou
          personne, ou cherchez.</li>
        <li><b>Une écriture :</b> cliquez-la dans le registre, puis <b>Historique</b>.</li>
        <li><b>Annuler :</b> les changements aux écritures et éléments prévus peuvent être annulés par toute personne qui peut
          modifier cet environnement : une écriture ajoutée disparaît, une modifiée redevient comme avant, une supprimée revient (un
          transfert avec ses deux côtés). Si elle a été modifiée de nouveau ensuite, annulez d'abord le changement le plus récent.
          Pour le reste, restaurez une sauvegarde.</li>
      </ul>` },
    allenvs: { title: "Voir plusieurs environnements ensemble", body: `
      <p>Avec des comptes dans plus d'un environnement (les privés dans l'un, ceux du ménage dans un autre), Accueil, Comptes,
      Factures et dépôts, Budget et Rapports ont un sélecteur d'<b>Environnements</b> en haut. Cochez ceux à voir ensemble, par
      exemple le personnel et celui du ménage mais pas l'entreprise. Celui où vous êtes est toujours inclus. <b>Tout</b> les coche
      tous; <b>Seulement</b> suivi du nom actuel décoche les autres. Le choix est le même sur chaque page et retenu dans ce navigateur.</p>
      <ul>
        <li>Tout s'additionne entre les environnements cochés; chaque élément indique où il se trouve. Un compte partagé entre deux
          d'entre eux compte une fois, et les transferts entre eux ne sont pas des dépenses.</li>
        <li>Les changements se font toujours dans l'environnement propre à l'élément : inscrire une facture, ouvrir un compte ou un
          relevé d'un autre environnement passe à celui-ci.</li>
        <li>Le budget combiné est pour consulter : les lignes de même catégorie s'additionnent. Les montants du budget se fixent dans
          chaque environnement.</li>
      </ul>` },
    signin: { title: "Connexion et mots de passe oubliés", body: `
      <p>Chaque personne a sa propre connexion. Changez votre nom, courriel ou mot de passe sous <b>Personnes → Votre connexion</b>.</p>
      <ul>
        <li><b>Rester connecté sur cet appareil :</b> coché à la connexion, vous restez connecté 30 jours, même après un redémarrage
          de l'ordinateur. Décoché (mieux sur les appareils partagés), vous êtes déconnecté quand le navigateur se ferme, ou après
          une heure sans utilisation. <b>Se déconnecter</b> y met fin tout de suite.</li>
        <li><b>Mot de passe oublié?</b> Sur la page de connexion, choisissez <i>Mot de passe oublié?</i>. Si votre connexion a une
          adresse courriel et qu'un administrateur a configuré le courriel (Paramètres → Notifications), MoneyThistle vous envoie un
          lien pour en choisir un nouveau. Le lien fonctionne une fois, pendant 30 minutes, depuis votre réseau domestique ou Tailscale.</li>
        <li><b>Pas de courriel?</b> Tout administrateur peut vous définir un nouveau mot de passe sous Personnes.</li>
        <li><b>Le seul administrateur, bloqué dehors :</b> sur l'ordinateur ou le serveur où MoneyThistle tourne, lancez
          <code>python main.py --reset-password VOTRE-NOM-D-UTILISATEUR</code> dans son dossier (avec Docker :
          <code>docker exec -it moneythistle python main.py --reset-password VOTRE-NOM-D-UTILISATEUR</code>).
          <code>--list-users</code> affiche les noms d'utilisateur.</li>
      </ul>
      <p>Chaque fois qu'un mot de passe change, chaque appareil qui l'utilise est déconnecté, et la personne reçoit un courriel à ce sujet (si elle a une adresse).</p>` },
    quick: { title: "Ajout rapide sur votre téléphone", body: `
      <p>Sur un téléphone, le bouton rond <b>+</b> (ou l'adresse <code>#/quick</code>) ouvre un écran fait pour un pouce :
      choisissez argent qui sort, argent qui entre ou un déplacement, tapez le montant, le bénéficiaire et le compte, et
      enregistrez. Ce qui est dû aujourd'hui peut aussi être inscrit de là.</p>
      <p>Ajoutez MoneyThistle à l'écran d'accueil de votre téléphone (dans le menu de partage ou du navigateur : <i>Ajouter à
      l'écran d'accueil</i>) et il s'ouvre comme une appli. Le téléphone doit pouvoir joindre MoneyThistle : sur votre réseau
      domestique, ou par Tailscale.</p>` },
    people: { title: "Personnes, environnements et partage", body: `
      <ul>
        <li><b>Personnes :</b> chacun se connecte avec son propre nom d'utilisateur et mot de passe. Les administrateurs ajoutent
          des connexions et réinitialisent les mots de passe.</li>
        <li><b>Environnements</b> : des ensembles de comptes distincts (Personnel, Entreprise, Beaux-parents…). Seuls les membres en
          voient un. Les propriétaires ajoutent des membres comme propriétaire, rédacteur (peut modifier) ou lecteur (consulte
          seulement). Changez en haut à droite.</li>
        <li><b>Comptes partagés :</b> afficher un compte aussi dans un autre environnement (votre compte chèques dans
          l'environnement de votre conjoint) : un registre, un solde, vus des deux côtés, avec ses factures et dépôts au choix.</li>
        <li><b>Connexions</b> : elles permettent de déplacer de l'argent entre environnements; « Transfert vers … » remplit l'autre côté.</li>
        <li><b>Déplacer des comptes :</b> pour donner un nouveau domicile à des comptes (par exemple de votre environnement Personnel
          vers un environnement du ménage que vous possédez tous les deux), ouvrez le compte, choisissez <b>Détails du compte →
          Déplacer vers un autre environnement…</b>, cochez chaque compte à déplacer ensemble et vérifiez ce qui se passera avant.
          Tout suit : opérations, éléments prévus, catégories et bénéficiaires. Les transferts vers des comptes qui restent
          deviennent des transferts entre environnements. Une sauvegarde est faite d'abord.</li>
      </ul>` },
    backups: { title: "Sauvegardes", body: `
      <p>MoneyThistle sauvegarde tout seul : après des changements, et selon un horaire. Chaque sauvegarde contient tout : tous les
      environnements et toutes les connexions.</p>
      <ul>
        <li><b>Où :</b> un dossier, et Nextcloud ou tout serveur WebDAV (utilisez un <i>mot de passe d'application</i> Nextcloud).
          Le dossier de sauvegarde là-bas est créé s'il n'existe pas.</li>
        <li><b>Vérifiée :</b> après chaque envoi, la copie est téléchargée de nouveau et comparée; une mauvaise copie est supprimée.
          <b>Vérifier</b> contrôle n'importe quelle sauvegarde sur demande.</li>
        <li><b>Chiffrement :</b> avec un mot de passe de sauvegarde, les sauvegardes ne peuvent pas être lues sans lui. Gardez ce mot
          de passe en sûreté : <b>un mot de passe perdu ne peut pas être récupéré</b>, ni ses sauvegardes.</li>
        <li><b>Jusqu'où :</b> les quelques dernières sauvegardes après changements, plus la dernière sauvegarde de chacun des 7
          derniers jours, 4 dernières semaines et 12 derniers mois. Une journée chargée ne peut pas faire disparaître la sauvegarde
          d'hier, donc une erreur trouvée plus tard peut encore être annulée. Les copies <b>Sauvegarder maintenant</b> sont gardées
          jusqu'à ce que vous les supprimiez. La liste indique pourquoi chacune est gardée.</li>
        <li><b>Restaurez</b> n'importe quelle sauvegarde depuis la page Sauvegardes. Tout revient comme c'était à ce moment (une copie
          de sécurité de maintenant est faite d'abord). Pour une écriture ou un élément prévu modifié par erreur,
          <b>Historique des changements → Annuler</b> est plus rapide et laisse tout le reste tel quel.</li>
      </ul>` },
    startover: { title: "Repartir d'une sauvegarde (nouvel ordinateur ou serveur)", body: `
      <p>L'ordinateur est mort, a été volé, ou vous déplacez MoneyThistle vers un serveur. Il vous faut seulement une sauvegarde :
      une sur Nextcloud, ou un fichier de sauvegarde (<code>money-…zip</code>, ou <code>.zip.enc</code> s'il est chiffré) et, s'il
      est chiffré, <b>son mot de passe de sauvegarde</b>.</p>
      <ol>
        <li><b>Installez MoneyThistle</b> sur le nouvel ordinateur ou serveur, comme la première fois : sur un ordinateur, le
          programme d'installation (ou le dossier MoneyThistle et <b>Start MoneyThistle</b>); sur un serveur, Docker Compose ou le
          script d'installation Unraid. Ne créez pas encore de connexion.</li>
        <li><b>Ouvrez-le dans le navigateur.</b> Une nouvelle installation affiche <i>Configurer MoneyThistle</i>. En dessous,
          ouvrez <b>Vous arrivez d'un autre ordinateur ou serveur? Partir plutôt d'une sauvegarde</b>.</li>
        <li><b>Choisissez la sauvegarde :</b> choisissez le fichier de sauvegarde et tapez son mot de passe, ou entrez l'adresse de
          votre dossier de sauvegarde Nextcloud, le nom d'utilisateur et le mot de passe d'application, choisissez
          <b>Afficher ses sauvegardes</b>, choisissez-en une (la plus récente en premier) et restaurez-la.</li>
        <li><b>Connectez-vous</b> avec votre nom d'utilisateur et mot de passe habituels. Tout est revenu : chaque environnement,
          compte, écriture, reçu, historique des changements et connexion.</li>
        <li><b>Vérifiez les Paramètres et les Sauvegardes.</b> Ils appartiennent à l'ordinateur, pas à la sauvegarde, donc
          configurez-les de nouveau : la connexion Nextcloud si vous avez restauré d'un fichier (depuis Nextcloud, elle est prête),
          les notifications, « Autres appareils » et le démarrage de MoneyThistle. Le mot de passe de sauvegarde tapé est gardé pour
          les nouvelles sauvegardes.</li>
      </ol>
      <ul>
        <li><b>Sur un serveur sans navigateur sous la main :</b> arrêtez MoneyThistle, puis lancez
          <code>python main.py --restore money-….zip.enc</code> dans son dossier (il demande le mot de passe de sauvegarde), et
          redémarrez-le.</li>
        <li><b>Déjà en marche et configuré?</b> Un administrateur utilise <b>Sauvegardes → Restaurer à partir d'un fichier…</b> (ou
          <b>Restaurer</b> à côté d'une sauvegarde de la liste). Une copie de sécurité de tout tel quel maintenant est enregistrée d'abord.</li>
        <li><b>Pratiquez une fois :</b> restaurer sur un ordinateur de rechange ou un conteneur de test est la seule preuve sûre que
          vos sauvegardes fonctionnent. <b>Vérifier</b> sur la page Sauvegardes contrôle qu'une sauvegarde s'ouvre sans rien changer.</li>
      </ul>` },
    simple: { title: "Simple ou Tout", body: `
      <p>Chaque personne choisit ce que MoneyThistle lui montre, dans <b>Paramètres → Apparence</b>. Les nouvelles connexions
      commencent en <b>Simple</b>.</p>
      <ul>
        <li><b>Simple</b> montre l'essentiel au quotidien. Les extras sont repliés sous <b>Plus d'options</b> (ou <b>Plus de
          champs</b>), prêts quand vous les voulez : le numéro, la note et l'état d'une écriture; les impôts et retenues détaillés
          d'un talon de paie; les coordonnées bancaires, taux et jours de carte d'un compte; le montant variable, l'inscription
          automatique et le dernier jour du mois d'un élément prévu; l'horaire des sauvegardes et d'autres endroits où les garder.
          Le déplacement de comptes entre environnements est laissé de côté, et la liste d'environnements en haut n'apparaît que
          s'il y en a plus d'un.</li>
        <li><b>Tout</b> ouvre tout.</li>
        <li>Ce que vous ouvrez ou fermez est retenu pour vous, endroit par endroit : ouvrez une fois les impôts d'un talon, et ils
          restent ouverts là.</li>
        <li>Rien de ce qui touche l'exactitude de vos chiffres n'est caché, et une section repliée indique <b>● rempli</b> quand
          quelque chose dedans a une valeur.</li>
      </ul>` },
    notifications: { title: "Notifications", body: `
      <p>Paramètres → Notifications envoie un résumé quotidien (ce qui est dû, ce qui a été inscrit automatiquement, les problèmes
      de sauvegarde) par courriel, Pushover, ntfy ou Gotify. Chaque personne configure le sien; le courriel peut utiliser les
      paramètres partagés qu'un administrateur a entrés, ou les siens.</p>` },
    startstop: { title: "Démarrer et arrêter MoneyThistle", body: `
      <p>MoneyThistle est un petit serveur; votre navigateur ne fait que l'afficher. <b>Fermer l'onglet du navigateur ne l'arrête
      pas</b>, car des téléphones et d'autres ordinateurs peuvent l'utiliser. Sur un ordinateur (pas Docker), un administrateur
      choisit dans <b>Paramètres → Cet ordinateur</b> :</p>
      <ul>
        <li><b>Menu Démarrer :</b> MoneyThistle s'y met lui-même la première fois qu'il démarre : <b>MoneyThistle</b> l'ouvre dans le
          navigateur, en le démarrant d'abord s'il ne tourne pas, et <b>Stop MoneyThistle</b> l'arrête. Une icône sur le bureau est
          proposée à l'installation, et dans les Paramètres.</li>
        <li><b>Quand je me connecte à cet ordinateur :</b> il démarre tout seul en arrière-plan chaque fois que vous vous connectez.</li>
        <li><b>Au démarrage de l'ordinateur, même si personne ne se connecte :</b> Windows le démarre chaque fois que l'ordinateur
          s'allume, donc un favori sur votre téléphone fonctionne toujours tant que l'ordinateur est allumé; vous ne le démarrez
          jamais vous-même. Ce choix demande une fois la permission d'administrateur Windows, alors faites-le dans un navigateur sur
          cet ordinateur. Pour l'arrêter, choisissez une des autres options (sans permission); MoneyThistle continue de tourner
          jusqu'à ce que vous l'arrêtiez ou redémarriez l'ordinateur. Sur Mac ou Linux, collez la commande affichée dans un terminal.</li>
        <li><b>⏻ Arrêter</b> (en haut de la page, administrateurs) : enregistre, fait sa sauvegarde et s'arrête. Personne ne peut
          l'ouvrir avant qu'il soit redémarré avec son icône (ou que l'ordinateur redémarre, s'il démarre avec l'ordinateur).</li>
        <li><b>Docker :</b> le conteneur démarre avec le serveur et le garde en marche; arrêtez-le avec <code>docker stop moneythistle</code>.</li>
      </ul>` },
    settings: { title: "Paramètres et mises à jour", body: `
      <ul>
        <li><b>Apparence :</b> clair ou sombre, couleur d'accent, style de date, et votre <b>langue</b> : anglais, français (Canada),
          espagnol (Amérique latine) ou portugais (Brésil). Les dates et montants suivent alors le style de cette langue. Les
          traductions ont été faites par une IA et n'ont pas encore été vérifiées par une personne de langue maternelle. Les noms que
          vous avez tapés (comptes, bénéficiaires, environnements) s'affichent toujours tels quels. Les catégories peuvent
          avoir un nom dans chaque langue (dans les détails de la catégorie, sous <i>Nom dans d'autres langues</i>); les
          catégories de départ les ont tous, et une catégorie sans nom dans une langue affiche son propre nom.</li>
        <li><b>Devises :</b> chaque compte a sa propre devise (dans ses détails) : les devises des Amériques et l'euro. Un transfert
          entre deux devises demande le montant réellement arrivé; aucun taux de change n'est cherché. Sous Apparence,
          <b>Devises</b> définit la principale (les totaux, le budget et le rapport fiscal y sont) et des taux approximatifs
          facultatifs pour les autres : la valeur nette et les rapports comptent les autres devises à ces taux, marqués
          approximatifs, et excluent une devise sans taux. Le rapport fiscal reste dans la devise principale.</li>
        <li><b>Autres appareils :</b> une copie qui tourne sur un ordinateur n'écoute que cet ordinateur, à moins que vous permettiez
          les autres appareils de votre réseau domestique (puis redémarriez). Les adresses pour l'ouvrir sont en bas de chaque page.</li>
        <li><b>Mises à jour :</b> quand des fichiers plus récents sont en place, un avis apparaît; <b>Redémarrer MoneyThistle</b> les
          applique. Vos données sont gardées.</li>
        <li><b>Où trouver les choses :</b> les fichiers de l'application, le dossier de données, les sauvegardes et le journal sont
          listés dans les Paramètres.</li>
      </ul>` },
    safety: { title: "Le garder en sécurité", body: `
      <p><b>N'exposez jamais MoneyThistle à l'Internet public</b> (pas de redirection de port, pas de mandataire inverse public).
      Utilisez-le sur votre réseau domestique ou par un RPV privé comme Tailscale. Il a une connexion, mais il n'est ni conçu ni
      testé pour résister aux attaques venant d'Internet, et personne ne peut garantir qu'une copie exposée publiquement est sûre.</p>
      <p>Utilisez un mot de passe fort pour chaque connexion, gardez des sauvegardes à plus d'un endroit et chiffrez celles qui
      quittent votre maison.</p>` },
  },
  faq: [
    { q: "MoneyThistle se connecte-t-il à ma banque?", a: `Non. Vous tapez les écritures, ou importez un fichier téléchargé de votre banque (OFX, QFX, QBO, CSV ou QIF). Rien ne va à une banque ni à personne d'autre.` },
    { q: "Pourquoi quelque chose n'apparaît pas dans le budget de ce mois?", a: `Vérifiez sa date : quelque chose inscrit pour un mois plus tard compte dans ce mois-là (le budget liste les éléments inscrits d'avance). Vérifiez aussi que sa catégorie est dans le budget et, pour les transferts, que ce sont des paiements (à une carte ou un prêt) et non des déplacements entre vos propres comptes.` },
    { q: "Quelle est la différence entre une facture et un transfert?", a: `Une facture est de l'argent qui part vers quelqu'un d'autre (orange −). Un transfert déplace de l'argent entre vos propres comptes (bleu ⇄); un transfert qui paie une carte de crédit ou un prêt compte comme dépense dans le budget par éléments prévus.` },
    { q: "Dois-je inscrire chaque achat par carte ou seulement le relevé?", a: `Les deux fonctionnent. Le solde du relevé est plus rapide : une écriture par mois. Inscrire les achats donne les dépenses par catégorie au fur et à mesure. Choisissez par carte dans ses Détails du compte; voir <a href="#/help/cards">Cartes de crédit</a>.` },
    { q: "Une opération s'est inscrite toute seule. Pourquoi?", a: `C'est un élément automatique de Factures et dépôts avec « l'inscrire pour moi » activé. Ceux-ci sont marqués ⟳ dans le registre. Désactivez-le sur l'élément si vous préférez l'inscrire vous-même.` },
    { q: "Comment corriger une erreur dans le registre?", a: `Cliquez l'écriture, choisissez <b>Modifier l'opération</b>, changez-la et choisissez <b>Enregistrer les changements</b>. Pour la retirer, utilisez la poubelle pendant la modification.` },
    { q: "Mon conjoint et moi pouvons-nous partager des comptes?", a: `Oui. Donnez à chaque personne sa propre connexion (Personnes), puis partagez un compte dans son environnement, ou faites-la membre du vôtre. Voir <a href="#/help/people">Personnes, environnements et partage</a>.` },
    { q: "Puis-je l'utiliser sur mon téléphone?", a: `Oui, dans le navigateur du téléphone, sur votre réseau domestique ou par Tailscale. L'Ajout rapide (le bouton +) est fait pour les téléphones. Voir <a href="#/help/quick">Ajout rapide</a>.` },
    { q: "Où sont gardées mes données?", a: `Dans le dossier de données indiqué sous Paramètres → Cet ordinateur : sur un ordinateur, votre propre dossier de données d'application; dans Docker ou Unraid, le dossier de données que vous avez associé. Les sauvegardes vont là où vous les avez configurées dans Paramètres → Sauvegardes.` },
    { q: "J'ai oublié le mot de passe de chiffrement des sauvegardes.", a: `Les sauvegardes chiffrées ne peuvent pas être ouvertes sans lui, c'est voulu. Votre fichier d'argent lui-même n'est pas touché : définissez un nouveau mot de passe dans Paramètres → Sauvegardes et faites une nouvelle sauvegarde tout de suite.` },
    { q: "Comment restaurer une sauvegarde?", a: `Paramètres → Sauvegardes → choisissez la sauvegarde → Restaurer. MoneyThistle fait d'abord une copie de sécurité de ce que vous avez.` },
    { q: "Restaurer une sauvegarde remet-il aussi l'ancienne version de MoneyThistle?", a: `Non : une restauration ramène vos données (comptes, écritures, reçus, personnes), jamais le programme. Le MoneyThistle que vous avez continue de tourner et lit les anciennes données. Une sauvegarde faite par un MoneyThistle <i>plus récent</i> que le vôtre est refusée jusqu'à ce que vous fassiez la mise à jour, pour que rien ne se perde ni ne se mélange.` },
    { q: "Est-il sécuritaire d'ouvrir MoneyThistle depuis Internet?", a: `Non : gardez-le sur votre réseau domestique ou Tailscale. Voir <a href="#/help/safety">Le garder en sécurité</a>.` },
    { q: "J'ai oublié mon mot de passe.", a: `Utilisez <i>Mot de passe oublié?</i> sur la page de connexion, demandez à un administrateur, ou voyez <a href="#/help/signin">Connexion et mots de passe oubliés</a> pour la façon de revenir qui fonctionne sans courriel.` },
    { q: "Puis-je apporter mon historique de Microsoft Money ou Quicken?", a: `Oui : chaque compte, catégorie et opération. Voir <a href="#/help/move-in">Emménager depuis un autre programme</a>.` },
    { q: "Comment revoir la visite?", a: `Choisissez <b>Faire la visite</b> en haut de cette page d'aide.` },
  ],
  terms: [
    { term: "Compte", def: "Un endroit où de l'argent est gardé ou dû : chèques, épargne, carte de crédit, prêt, placement." },
    { term: "Registre", def: "La liste des écritures d'un compte avec son solde courant, comme un carnet de chèques." },
    { term: "Opération (écriture)", def: "Une ligne dans un registre : de l'argent qui entre ou sort à une date." },
    { term: "Bénéficiaire", def: "À qui vous avez payé ou qui vous a payé." },
    { term: "Catégorie", def: "À quoi a servi l'argent (Épicerie, Loyer) ou d'où il vient (Salaires). Les catégories principales peuvent avoir des sous-catégories." },
    { term: "Lié aux impôts", def: "Une catégorie dont les écritures vont dans le rapport fiscal de fin d'année. À définir sous Catégories." },
    { term: "Transfert (déplacer)", def: "De l'argent qui passe entre deux de vos propres comptes : une écriture dans chaque registre, gardées ensemble." },
    { term: "Ventilé", def: "Un paiement fait de parties dans différentes catégories ou comptes, comme un paiement de prêt (capital, intérêts, entiercement) ou un talon de paie." },
    { term: "Compensé (C)", def: "Votre banque a traité l'écriture." },
    { term: "Rapproché (R)", def: "L'écriture a été comparée à un relevé avec Concilier le compte." },
    { term: "Élément prévu", def: "Une facture, un dépôt, un transfert ou un paiement dans Factures et dépôts qui se répète." },
    { term: "Automatique ⟳", def: "Un élément prévu qui se fait tout seul; avec « l'inscrire pour moi », MoneyThistle l'inscrit à sa date." },
    { term: "Solde du relevé", def: "Ce que le relevé d'une carte dit que vous devez à sa date de fermeture." },
    { term: "Jour de fermeture / d'échéance", def: "Le jour où le relevé d'une carte ferme, et le jour où son paiement est dû. 31 veut dire le dernier jour du mois." },
    { term: "Salaire brut", def: "La paie avant impôts et retenues." },
    { term: "Salaire net", def: "Ce qui arrive dans votre compte après impôts et retenues." },
    { term: "Retenue avant impôts", def: "Prise sur la paie avant l'impôt sur le revenu, comme un 401(k), un HSA par la paie ou une assurance maladie. Elle réduit le salaire imposable (W-2 case 1)." },
    { term: "HSA", def: "Compte d'épargne-santé (États-Unis) : de l'argent pour les frais médicaux avec des avantages fiscaux, jusqu'à un plafond annuel pour tous vos HSA." },
    { term: "Environnement", def: "Un ensemble de comptes distinct (Personnel, Entreprise…) que seuls ses membres voient." },
    { term: "Compte partagé", def: "Un compte affiché aussi dans un autre environnement : un registre et un solde vus des deux côtés." },
    { term: "Valeur nette", def: "Tout ce que vous avez moins tout ce que vous devez." },
    { term: "Prévision", def: "Les soldes projetés à partir d'aujourd'hui selon votre calendrier (Rapports → Prévisions)." },
    { term: "WebDAV", def: "Une façon standard de stocker des fichiers sur un serveur; Nextcloud le parle. Sert aux sauvegardes." },
    { term: "Tailscale", def: "Un réseau privé entre vos propres appareils, pour qu'un téléphone loin de la maison joigne MoneyThistle sans l'exposer à Internet." },
  ],
});
