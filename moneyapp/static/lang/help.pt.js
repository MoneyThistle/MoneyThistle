// Ajuda do MoneyThistle em português (Brasil). Traduzida por IA; ainda não revisada por um falante nativo.
"use strict";
I18N.helpText({
  guides: {
    about: { title: "Sobre o MoneyThistle", body: `
      <p><b>Por que ele existe.</b> Durante anos, o Microsoft Money Plus Sunset foi o último de uma coisa boa: um programa de
      finanças gratuito e off-line que guardava tudo no seu próprio computador. A Microsoft parou de fazer o Money há muito tempo, e
      a edição Sunset só envelhece. O MoneyThistle nasceu do desejo de uma família de manter esse jeito de fazer as coisas, só que mais
      simples: as mesmas contas, extratos, contas a pagar, orçamento e relatórios, rodando em casa (num computador, num servidor
      doméstico ou no Docker), aberto em qualquer navegador nos computadores e celulares da família, sem conexão com bancos e com
      backups automáticos no Nextcloud ou lugares parecidos. A ideia é que qualquer pessoa da família consiga usar, não só quem instalou.</p>
      <p>Ele foi construído depois de estudar como o Money Plus Sunset se comporta (suas categorias, tipos de conta, agendas de
      contas e regras de backup) e então escrito do zero; não contém nenhum código da Microsoft.</p>
      <p><b>Como foi feito: "vibe coding".</b> Para deixar claro desde já: o MoneyThistle foi escrito por uma IA. Quase todo o
      código, as telas, esta Ajuda e os testes automáticos foram produzidos pelo Claude, da Anthropic, a partir de pedidos em
      linguagem simples. O mantenedor humano decidiu o que ele devia fazer e como devia ser, usou e testou cada recurso, apontou o
      que estava errado e pediu de novo até funcionar. O mantenedor não revisou o código linha por linha.</p>
      <p><b>O que isso significa para você.</b> O MoneyThistle tem um conjunto de testes automáticos e uso real no dia a dia, mas
      não passou por revisão profissional de código nem auditoria de segurança. Então:</p>
      <ul>
        <li>Mantenha backups (o MoneyThistle faz sozinho; de vez em quando confira se eles são verificados).</li>
        <li>Mantenha-o na sua rede de casa ou no Tailscale, nunca aberto para a internet pública.</li>
        <li>Confira os números importantes com os extratos do banco e do cartão, como faria com qualquer programa de finanças.</li>
        <li>Se você sabe ler código: revisões, relatos de erros e correções são muito bem-vindos.</li>
      </ul>
      <p><b>Software livre.</b> O MoneyThistle é livre e de código aberto sob a GNU AGPL-3.0, e vem sem nenhuma garantia. Você pode
      usar, alterar e compartilhar; uma versão alterada que você ofereça a outras pessoas, inclusive como site, também precisa
      compartilhar as alterações. O link no rodapé de cada página baixa o código-fonte exatamente desta cópia. Ele não coleta
      nenhum dado seu e não envia nada a lugar nenhum, a não ser para onde você mandar (seus backups e notificações).</p>` },
    start: { title: "Primeiros passos", body: `
      <p>O MoneyThistle guarda o dinheiro da sua casa num só lugar: contas e seus extratos, contas a pagar e depósitos numa agenda,
      um orçamento mensal, relatórios e backups automáticos. Não há conexão com o banco: você digita os lançamentos, ou traz de um
      arquivo que o seu banco deixa baixar.</p>
      <ol>
        <li><b>Adicione suas contas</b> (Contas → Novo): corrente, poupança, cartões de crédito, empréstimos, investimentos.
          Informe o saldo de cada uma numa data e, para cartões e empréstimos, quanto você deve.</li>
        <li><b>Coloque contas e salários regulares na agenda</b> (Contas e depósitos) para o Início mostrar o que vem por aí e o
          orçamento saber o que esperar.</li>
        <li><b>Registre o que acontece</b> no extrato de cada conta, ou com o <a href="#/help/quick">Lançamento rápido</a>
          no celular.</li>
        <li><b>Ative os backups</b> (Backups): uma pasta e, de preferência, também o Nextcloud ou outro servidor WebDAV.</li>
      </ol>
      <p>Personalize o Início com <b>Personalizar</b> na página Início. Refaça o tour quando quiser a partir desta página de Ajuda.</p>` },
    register: { title: "As contas e o extrato", body: `
      <p>Cada conta tem um <b>extrato</b>: todos os lançamentos com data, favorecido, categoria, valor e o saldo corrente.
      Digite um novo na linha de baixo: escolha <b>Saque</b> ou <b>Depósito</b> e preencha o favorecido; o MoneyThistle lembra a
      categoria e o valor habituais de cada favorecido.</p>
      <ul>
        <li><b>Alterar um lançamento:</b> clique nele no extrato. Ele aparece na linha de baixo, travado; escolha
          <b>Editar lançamento</b>, altere e depois <b>Salvar alterações</b> (ou <b>Cancelar</b>). A lixeira o exclui.</li>
        <li><b>Holerites e pagamentos divididos</b> aparecem em uma linha; <i>▸ partes</i> mostra cada parte (impostos,
          descontos, principal e juros), e clicar na linha o abre. Feche qualquer janela com ✕, Esc ou um clique ao lado:
          se algo mudou, ela pergunta se deve salvar antes.</li>
        <li><b>Transferências:</b> como categoria, escolha "Transferência para …" outra conta. O lançamento correspondente é
          adicionado sozinho à outra conta.</li>
        <li><b>Lançamentos divididos</b> (um pagamento de empréstimo, um holerite) aparecem como uma linha com as partes embaixo.</li>
        <li><b>Com data depois de hoje:</b> os lançamentos de dias que ainda vão chegar têm uma barra à esquerda e um fundo sombreado, para separar bem o passado do futuro.</li>
        <li><b>Ordem:</b> "Mais recentes primeiro" inverte a ordem. Lançamentos do mesmo dia podem ser movidos com ▲ ▼.</li>
        <li><b>Compensado e conciliado:</b> clique na coluna de situação para marcar um lançamento como compensado (C) ou
          conciliado (R). <b>Conciliar a conta</b> guia você para conferir um extrato do banco.</li>
        <li><b>Detalhes da conta</b> guardam o banco, o número da conta, o site, o telefone e a taxa de juros e, nos cartões, o
          limite e os dias da fatura.</li>
        <li><b>Favoritas e ordem:</b> clique na ☆ ao lado de uma conta na lista para torná-la favorita (★); as favoritas vêm primeiro no grupo.
          Para mudar a ordem, abra o 🔒 no alto da lista, arraste uma conta (no celular, ▲ ▼) e feche de novo; sair de Contas também fecha.
          Favoritas e ordem são só suas: cada pessoa que usa as mesmas contas mantém as suas.</li>
        <li><b>Um salário com o holerite:</b> um clique o mostra na linha de baixo como qualquer lançamento, com <b>Recibos</b> (guarde ali o PDF do holerite)
          e <b>Holerite</b>, que abre o holerite. A etiqueta verde <b>Holerite</b> na linha o abre direto.</li>
      </ul>` },
    balances: { title: "Saldo e saldo compensado", body: `
      <p>Cada conta mostra dois totais lado a lado.</p>
      <ul>
        <li>O <b>saldo</b> conta tudo o que está no extrato: cada lançamento, compensado ou não, inclusive os com data depois de hoje.</li>
        <li>O <b>saldo compensado</b> conta só os lançamentos marcados como compensados (C) ou conciliados (R): o que o banco já viu. É ele que se compara com o saldo do banco.</li>
        <li><b>Por que diferem:</b> cheques ainda não descontados, compras no cartão pendentes, depósitos ainda não lançados e lançamentos com data futura contam no saldo, mas não no compensado.</li>
        <li><b>Quando olhar com atenção:</b> uma diferença que vai e volta é normal. Uma que só cresce, ou lançamentos de semanas atrás ainda não compensados, costuma indicar algo que nunca chegou ao banco ou foi lançado duas vezes.
          <b>Conciliar a conta</b> percorre um extrato e marca o que confere. Uma conta nunca conciliada mostra uma diferença grande só porque nada foi marcado ainda.</li>
      </ul>` },
    cards: { title: "Cartões de crédito", body: `
      <p>Cada cartão é controlado de um de dois jeitos (Detalhes da conta → <i>Como você controla este cartão?</i>):</p>
      <ul>
        <li><b>Saldo da fatura:</b> uma vez por mês você lança o saldo da fatura; um lançamento leva o cartão ao que ele deve.
          Com o dia de fechamento preenchido, o Início avisa quando uma fatura fechou.</li>
        <li><b>Cada compra:</b> você lança cada compra. O orçamento por itens agendados mostra as compras do mês como pendentes,
          pagas depois pelo pagamento do cartão, para nada contar duas vezes.</li>
      </ul>
      <p><b>Pagar um cartão:</b> uma transferência da conta corrente para o cartão. Um botão oferece o saldo da última fatura
      (menos o que já foi pago desde então). Marque <i>Manter o pagamento do cartão na minha agenda</i> para ter o pagamento em
      Contas e depósitos todo mês no dia do vencimento.</p>
      <p><b>Um cartão para um só tipo de gasto</b> (despesas elegíveis à HSA, doações, uma empresa): escolha em
      <i>Para que serve este cartão?</i>. As compras e faturas dele vão sozinhas para essa categoria.</p>
      <p><b>Último dia do mês:</b> digite 31 no dia de fechamento ou de vencimento. Meses mais curtos usam o último dia;
      29 e 30 funcionam do mesmo jeito em fevereiro.</p>` },
    receipts: { title: "Recibos e outros arquivos", body: `
      <p>Guarde a foto do recibo, ou um PDF (uma nota fiscal, uma garantia, uma conta médica para a sua HSA), junto com o
      lançamento a que pertence.</p>
      <ul>
        <li><b>No celular:</b> embaixo de um novo lançamento, <b>📷 Tirar foto</b> abre a câmera; a foto é anexada quando você
          aperta Lançar. <b>Escolher uma foto ou arquivo</b> pega um que você já tem.</li>
        <li><b>Depois:</b> escolha o lançamento no extrato e clique em <b>Recibos</b> para adicionar mais, abrir, baixar ou remover.
          Lançamentos com algo anexado mostram um clipe.</li>
        <li><b>Documentos guardados com uma conta:</b> num cartão em que você só lança faturas e pagamentos, não há lançamento para
          a TV que você comprou. Escolha <b>Documentos</b> na página da conta para guardar o recibo, a garantia ou o contrato com a
          própria conta, com a data a que se refere.</li>
        <li><b>Observações e palavras-chave:</b> dê a qualquer arquivo uma observação curta ("TV, garantia 2 anos, série 12345")
          ao adicionar, ou depois embaixo dele. Tudo o que você digita é salvo quando sai do campo.</li>
        <li><b>Arquivos</b> (no menu) lista todos os recibos e documentos deste ambiente, mais recentes primeiro. Pesquise por
          qualquer palavra da observação, do nome do arquivo, do favorecido ou da conta; filtre por uma conta ou um período;
          clique numa coluna para ordenar.</li>
        <li>As fotos são reduzidas antes de serem enviadas (cerca de 400 KB em vez de vários MB); um PDF pode ter até 20 MB.</li>
        <li>Os arquivos ficam na pasta de dados e entram em todo backup, inclusive no Nextcloud.</li>
        <li>Excluir um lançamento deixa os arquivos dele guardados por 60 dias, então desfazer a exclusão (Histórico) os traz de volta.</li>
      </ul>` },
    paystubs: { title: "Salários e holerites", body: `
      <p>Registre um salário com o que você souber. O <b>salário líquido</b> (o que chegou no banco) é suficiente; o salário bruto
      e os descontos do holerite podem vir agora ou depois. Na conta onde o salário cai, escolha <b>Holerite…</b> acima da linha
      de lançamento. Só o salário líquido é obrigatório.</p>
      <ul>
        <li><b>Outros descontos:</b> quando você informa o salário bruto, o que não estiver detalhado (bruto menos líquido menos
          os descontos digitados) aparece e é salvo como <b>Outros descontos</b>. Detalhe o quanto quiser; em 0 tudo está
          detalhado. Se os descontos passarem do bruto menos o líquido, o holerite só pode ser salvo quando os valores baterem.</li>
        <li><b>Adicionado após impostos:</b> dinheiro no salário líquido que não é salário (um reembolso de despesas, uma
          devolução). Adicione em <b>+ Algo adicionado após impostos</b> para não esconder um desconto.</li>
        <li><b>Salários agendados:</b> em Contas e depósitos, marque <b>É um salário</b> no depósito (o valor dele é o salário
          líquido, ou a média). Quando vencer, <b>Lançar</b> oferece <b>Registrar só o salário líquido</b> ou
          <b>Preencher o holerite</b>.</li>
        <li><b>Adicionar detalhes depois:</b> um salário registrado só com o líquido aparece marcado como <b>Salário</b> no
          extrato; abra e escolha <b>Adicionar detalhes do holerite</b>.</li>
        <li><b>O que falta é sinalizado:</b> o MoneyThistle aprende o que é normal para cada empregador (só líquido, bruto e
          líquido, ou cada imposto e desconto) pelos últimos salários. Um salário com menos que o normal mostra <b>⚑</b> no
          extrato (<i>falta o salário bruto</i>, <i>falta: Medicare</i>, ou <i>R$ 220,00 não detalhados</i> quando os holerites
          desse empregador costumam ser todos detalhados), e o relatório fiscal de fim de ano lista esses em
          <b>Salários a verificar</b>. Se bruto e líquido é o seu normal, Outros descontos nunca são sinalizados; se só o líquido
          é o seu normal, nada é. <b>Completo assim</b> para a sinalização de um que não terá mais detalhes.</li>
        <li>Cada imposto ou desconto vai para uma categoria (Imposto de renda federal, Seguros : Saúde…) ou para uma das suas
          contas (previdência, HSA), onde aparece como dinheiro entrando. Não acompanha essa conta no MoneyThistle? Use <b>Poupança e investimentos</b>
          (Plano de previdência, Conta de saúde). Cada novo holerite começa como cópia do anterior;
          mova as linhas com ▲ ▼ (ou Alt+↑ ↓) para seguir a ordem do seu holerite.</li>
        <li><b>Salário depositado em mais de uma conta</b> (R$ 250 na poupança, R$ 3.210,14 na corrente): em <i>Depositado em</i>,
          escolha <i>+ Adicionar uma conta</i> e informe o que chegou em cada uma. O salário líquido é o total delas. Funciona
          também só com o salário líquido. O valor de um pagamento agendado pode ser o total ou o que chega na própria conta. Um depósito agendado também pode ter mais de uma conta (Contas e depósitos, <i>+ Adicionar uma conta</i>), cada uma
          com valor fixo ou a média do que recebeu antes; elas são registradas juntas.</li>
        <li>No orçamento, um salário conta pelo valor líquido. Os relatórios mostram cada linha, e o relatório fiscal de fim de
          ano mostra bruto x líquido de cada empregador.</li>
      </ul>` },
    bills: { title: "Contas e depósitos (a agenda)", body: `
      <p>Tudo o que se repete: contas, salários, transferências para a poupança, pagamentos de empréstimo e de cartão. Cada item
      tem uma conta, um valor e uma frequência, de diária a anual (ou só uma vez). Um item mensal pode cair no
      <b>último dia do mês</b>.</p>
      <ul>
        <li><b>Lançar</b> registra o próximo no extrato (você pode mudar o valor e a data antes); <b>Pular</b> passa um que não
          aconteceu. Um recibo, fatura ou holerite pode ir junto: escolha <b>Adicionar um recibo ou arquivo</b> (ou
          <b>Tirar foto</b> no celular) antes de registrar.</li>
        <li><b>Valor variável:</b> a agenda espera a média dos últimos lançados.</li>
        <li><b>Automático ⟳:</b> marque os itens que acontecem sozinhos (débito automático, depósito direto). Escolha
          <i>lançar para mim</i> e o MoneyThistle registra cada um na data, marcado com ⟳ no extrato.</li>
        <li>O Início lista o que vence em breve; Relatórios → Previsão usa a agenda para prever os saldos.</li>
        <li><b>Em breve</b> mostra cada vez que um item acontece nos dias escolhidos. Só o primeiro pode ser lançado ou pulado; os seguintes mostram o que vem por aí.
          A conta com mais itens vem primeiro, e os cartões preenchem as colunas para que um longo não deixe um vazio ao lado.</li>
        <li><b>Mostrar automáticos</b> (marcado) inclui também os itens automáticos; desmarque para ver só o que precisa de você. Sua escolha é lembrada em todos os seus aparelhos.</li>
        <li><b>Pagar esta conta ↗</b> abre o site onde a conta é paga: digite-o em <i>Mais opções</i> (<i>Site para pagá-la</i>). Pagamentos de cartão e de empréstimo usam o site dos detalhes do cartão ou do empréstimo.
          Depósitos e transferências têm <b>Ver conta ↗</b>, para o site da conta.</li>
        <li><b>Uma média:</b> clique no valor médio de um item agendado para ver os valores de onde ela vem, com as datas.</li>
      </ul>
      <p>Cores e símbolos: dinheiro que entra é verde <b>+</b>, dinheiro que sai é laranja <b>−</b>, movimentações entre suas
      próprias contas são azuis <b>⇄</b>.</p>` },
    budget: { title: "O orçamento", body: `
      <p>Dois estilos; troque com os botões no topo da página Orçamento:</p>
      <ul>
        <li><b>Por categoria:</b> cada categoria do orçamento recebe um valor mensal. Deixe uma em 0 e ela espera o que a sua
          agenda tem para ela naquele mês. Os gastos aparecem em cada linha conforme acontecem.</li>
        <li><b>Por itens agendados:</b> para quem não acompanha categorias. Cada conta, depósito e transferência da agenda é uma
          linha: o que se espera neste mês e o que já foi lançado.</li>
      </ul>
      <p>Pagamentos de empréstimo contam inteiros (principal, juros e caução juntos). Holerites contam pelo salário líquido.
      Algo lançado antes com a data do mês que vem conta no mês que vem; o orçamento avisa.</p>` },
    reports: { title: "Relatórios", body: `
      <ul>
        <li><b>Para onde vai / de onde vem o dinheiro:</b> totais por categoria num período. Clique numa para ver os lançamentos.</li>
        <li><b>Receitas x gastos:</b> mês a mês no último ano.</li>
        <li><b>Patrimônio líquido ao longo do tempo:</b> tudo o que você tem menos tudo o que deve, mês a mês.</li>
        <li><b>Previsão:</b> o saldo de cada conta dia a dia a partir de hoje, usando a sua agenda. Marque contas para
          desenhá-las; clique num item agendado para marcar o dia dele.</li>
        <li><b>Impostos:</b> veja <a href="#/help/taxes">o relatório fiscal de fim de ano</a>.</li>
      </ul>
      <p>As contas compartilhadas com este ambiente estão incluídas.</p>` },
    taxes: { title: "O relatório fiscal de fim de ano", body: `
      <p>Relatórios → <b>Impostos</b> reúne tudo nas categorias marcadas como <b>Relacionado a impostos</b> (defina isso em
      Categorias) de um ano-calendário, com cada lançamento listado: receitas e depois deduções e despesas. Baixe como planilha
      ou imprima (ou salve em PDF) para o seu contador.</p>
      <ul>
        <li><b>Salário:</b> com holerites lançados, bruto x líquido de cada empregador e cada imposto e desconto.
          Não é preciso digitar o W-2: compare estes totais com o W-2 que o empregador envia.</li>
        <li><b>Contas de poupança para saúde (HSA):</b> marque uma conta como HSA nos detalhes e diga quem deposita dinheiro.
          O relatório soma os seus depósitos após impostos (dedutíveis) e os antes dos impostos (do empregador ou da folha, no
          seu W-2) em <i>todas</i> as suas HSAs, compara com o limite anual que você informa e lista as retiradas. Os seus
          próprios depósitos feitos de 1º de janeiro a 15 de abril podem contar para o ano anterior.</li>
        <li><b>Outras moedas:</b> o relatório fica na moeda principal; as contas em outras moedas são listadas para você somar
          com as cotações oficiais.</li>
      </ul>
      <p>É um resumo para conferir com seus formulários fiscais, não orientação fiscal.</p>` },
    import: { title: "Importar do seu banco", body: `
      <p>No extrato de uma conta, escolha <b>Importar arquivo</b> e um arquivo baixado do site do seu banco:
      <b>OFX, QFX ou QBO</b> (o melhor: trazem os identificadores do próprio banco), <b>CSV</b> (uma planilha com colunas Data e
      Valor, ou Débito/Crédito) ou <b>QIF</b>.</p>
      <p>Antes de adicionar qualquer coisa você vê uma revisão: lançamentos iguais a um que você já tem (mesmo valor em poucos
      dias) são associados em vez de duplicados; duplicatas exatas são puladas; o resto você decide.
      Importar o mesmo arquivo OFX duas vezes não adiciona nada.</p>` },
    "move-in": { title: "Trazer tudo de outro programa", body: `
      <p>Configurações → <b>Trazer tudo de outro programa…</b> traz cada conta e o histórico dela de uma vez.</p>
      <ul>
        <li><b>Microsoft Money:</b> Arquivo → Exportar, uma vez por conta (Loose QIF serve). Escolha todos os arquivos juntos;
          cada conta pega o nome real do saldo inicial, e as transferências entre elas se casam.</li>
        <li><b>Quicken, Moneydance, KMyMoney, HomeBank, Money Manager Ex, Banktivity:</b> exporte tudo para um arquivo QIF.</li>
        <li><b>YNAB, GnuCash, Actual Budget, Mint, Firefly III:</b> o CSV de exportação de todas as transações. Qualquer outro CSV
          funciona quando tem colunas Conta, Data, Favorecido, Categoria e Valor.</li>
      </ul>
      <p>Primeiro você vê o que há no arquivo: cada conta com seus lançamentos, datas e saldo, e as categorias que seriam
      adicionadas. Para cada conta escolha uma conta nova, uma que você já tem, ou deixar de fora. Nada muda até
      <b>Importar</b>.</p>
      <p>Vem: contas, saldos iniciais, categorias, favorecidos e cada transação com divisões, transferências e marcas de
      compensado. Não vem: contas agendadas, orçamentos e posições de investimento. Lançamentos que já estão numa conta escolhida
      não são adicionados duas vezes. Faça um backup antes; o download do banco de uma só conta continua passando por
      <a href="#/help/import">Importar arquivo</a>.</p>
      <p>Para montar sua agenda de novo, abra um registro e clique numa conta, salário ou transferência que se repete, depois em
      <b>Agendar…</b>. Um novo item agendado é preenchido a partir desse lançamento: o favorecido, a conta, a categoria e o valor, e
      a frequência e a próxima data pelos outros lançamentos do mesmo favorecido nessa conta (um valor que muda fica variável, pela
      média). Confira e salve.</p>
      <p>Um empréstimo ou financiamento chega como uma simples conta de empréstimo, sem a taxa e o pagamento. Abra a conta e escolha
      <b>Configurar detalhes do empréstimo…</b>: eles são preenchidos a partir dos pagamentos (confira com um extrato), e então
      ela tem cronograma de pagamentos, data de quitação e <b>E se…</b>. O registro e o saldo ficam como estão.</p>` },
    history: { title: "Histórico de alterações e desfazer", body: `
      <p>O MoneyThistle registra cada lançamento, item agendado, conta, categoria e valor de orçamento adicionado, alterado ou
      excluído: quem fez, quando, em qual ambiente e como estava antes e depois. Fica guardado por um ano e entra em todo backup.</p>
      <ul>
        <li><b>Tudo:</b> Pessoas → <b>Histórico de alterações</b> (ou Configurações → Seus dados). Filtre por ambiente ou pessoa,
          ou pesquise.</li>
        <li><b>Um lançamento:</b> clique nele no extrato e depois em <b>Histórico</b>.</li>
        <li><b>Desfazer:</b> alterações em lançamentos e itens agendados podem ser desfeitas por quem pode alterar aquele ambiente:
          um lançamento adicionado some, um alterado volta ao que era, um excluído volta (uma transferência com os dois lados).
          Se foi alterado de novo depois, desfaça primeiro a alteração mais recente. Para o resto, restaure um backup.</li>
      </ul>` },
    allenvs: { title: "Ver vários ambientes juntos", body: `
      <p>Com contas em mais de um ambiente (as particulares num, as da casa em outro), Início, Contas, Contas e depósitos,
      Orçamento e Relatórios têm um seletor de <b>Ambientes</b> no topo. Marque os que quer ver juntos, por exemplo o pessoal e
      o da casa, mas não o da empresa. Aquele em que você está sempre entra. <b>Todos</b> marca cada um; <b>Só</b> seguido do
      nome atual desmarca o resto. A escolha vale em todas as páginas e é lembrada neste navegador.</p>
      <ul>
        <li>Tudo é somado entre os ambientes marcados; cada item mostra em qual está. Uma conta compartilhada entre dois deles
          conta uma vez, e transferências entre eles não são gastos.</li>
        <li>As alterações continuam sendo feitas no ambiente do próprio item: lançar uma conta, abrir uma conta ou uma fatura
          de outro ambiente muda para ele.</li>
        <li>O orçamento combinado é para olhar: linhas com a mesma categoria se somam. Os valores do orçamento são definidos em
          cada ambiente.</li>
      </ul>` },
    signin: { title: "Login e senhas esquecidas", body: `
      <p>Cada pessoa tem o próprio acesso. Mude seu nome, e-mail ou senha em <b>Pessoas → Seu acesso</b>.</p>
      <ul>
        <li><b>Manter conectado neste dispositivo:</b> marcado ao entrar, você fica conectado por 30 dias, inclusive depois de
          reiniciar o computador. Desmarcado (melhor em dispositivos compartilhados), você sai quando o navegador fecha, ou
          depois de uma hora sem uso. <b>Sair</b> encerra na hora.</li>
        <li><b>Esqueceu a senha?</b> Na página de login escolha <i>Esqueceu a senha?</i>. Se o seu acesso tem e-mail e um
          administrador configurou o e-mail (Configurações → Notificações), o MoneyThistle envia um link para escolher uma nova.
          O link vale uma vez, por 30 minutos, a partir da sua rede de casa ou do Tailscale.</li>
        <li><b>Sem e-mail?</b> Qualquer administrador pode definir uma nova senha para você em Pessoas.</li>
        <li><b>O único administrador, sem acesso:</b> no computador ou servidor onde o MoneyThistle roda, execute
          <code>python main.py --reset-password SEU-USUARIO</code> na pasta dele (com Docker:
          <code>docker exec -it moneythistle python main.py --reset-password SEU-USUARIO</code>).
          <code>--list-users</code> mostra os nomes de usuário.</li>
      </ul>
      <p>Sempre que uma senha muda, cada dispositivo que a usa é desconectado, e a pessoa recebe um e-mail avisando (quando tem endereço).</p>` },
    quick: { title: "Lançamento rápido no celular", body: `
      <p>No celular, o botão redondo <b>+</b> (ou o endereço <code>#/quick</code>) abre uma tela feita para um polegar: escolha
      dinheiro saindo, entrando ou uma movimentação, digite o valor, o favorecido e a conta, e salve. O que vence hoje também
      pode ser lançado dali.</p>
      <p>Adicione o MoneyThistle à tela inicial do celular (no menu de compartilhar ou do navegador: <i>Adicionar à tela
      inicial</i>) e ele abre como um app. O celular precisa alcançar o MoneyThistle: na sua rede de casa ou pelo Tailscale.</p>` },
    people: { title: "Pessoas, ambientes e compartilhamento", body: `
      <ul>
        <li><b>Pessoas:</b> cada um entra com o próprio nome de usuário e senha. Administradores adicionam acessos e redefinem senhas.</li>
        <li><b>E-mail de boas-vindas:</b> com o e-mail configurado (Configurações › Notificações), ao adicionar alguém dá para enviar boas-vindas:
          quem adicionou, o nome de usuário, os endereços para abrir o MoneyThistle, o que a pessoa pode ver e um link para escolher a
          própria senha (funciona uma vez, por 3 dias). <b>Enviar boas-vindas</b> na lista envia de novo.</li>
        <li><b>Um cartão pago de outro ambiente:</b> nos detalhes de um cartão, <b>Pagar com</b> também lista contas de outros
          ambientes que são seus. O pagamento fica onde o dinheiro sai (por exemplo a conta corrente do Household), conectado
          sozinho, e aparece também em Contas e depósitos e no Início do cartão.</li>
        <li><b>Ambientes</b> são grupos de contas separados (Pessoal, Empresa, Sogros…). Só os membros veem um ambiente. Os donos
          adicionam membros como dono, editor (pode alterar) ou leitor (só olha). Troque no canto superior direito.</li>
        <li><b>Contas compartilhadas:</b> mostre uma conta também em outro ambiente (sua conta corrente no ambiente do seu
          cônjuge): um extrato, um saldo, visto nos dois, opcionalmente com as contas e depósitos dela.</li>
        <li><b>Conexões</b> permitem mover dinheiro entre ambientes: "Transferência para …" preenche o outro lado.</li>
        <li><b>Mover contas:</b> para dar um novo lar às contas (por exemplo, do seu ambiente Pessoal para um da casa que vocês
          dois têm), abra a conta, escolha <b>Detalhes da conta → Mover para outro ambiente…</b>, marque todas as contas que vão
          juntas e confira o que vai acontecer antes. Tudo vai junto: lançamentos, itens agendados, categorias e favorecidos.
          Transferências para contas que ficam viram transferências entre ambientes. Um backup é feito antes.</li>
      </ul>` },
    backups: { title: "Backups", body: `
      <p>O MoneyThistle faz backup sozinho: depois de alterações e numa agenda. Cada backup guarda tudo: todos os ambientes e acessos.</p>
      <ul>
        <li><b>Onde:</b> uma pasta, e o Nextcloud ou qualquer servidor WebDAV (use uma <i>senha de aplicativo</i> do Nextcloud).
          A pasta de backup lá é criada se não existir.</li>
        <li><b>Verificado:</b> depois de cada envio a cópia é baixada de novo e comparada; uma cópia ruim é excluída.
          <b>Verificar</b> confere qualquer backup quando você pedir.</li>
        <li><b>Criptografia:</b> com uma senha de backup, os backups não podem ser lidos sem ela. Guarde essa senha bem:
          <b>uma senha perdida não pode ser recuperada</b>, nem os backups dela.</li>
        <li><b>Até quando:</b> os poucos backups mais recentes feitos após alterações, mais o último backup de cada um dos últimos
          7 dias, 4 semanas e 12 meses. Um dia cheio de alterações não empurra para fora o backup de ontem, então um erro
          descoberto depois ainda pode ser desfeito. Cópias de <b>Fazer backup agora</b> ficam até você excluí-las. A lista diz
          por que cada uma é mantida.</li>
        <li><b>Restaure</b> qualquer backup pela página Backups. Tudo volta a como estava (antes é feita uma cópia de segurança
          de agora). Para um lançamento ou item agendado alterado por engano, <b>Histórico de alterações → Desfazer</b> é mais
          rápido e deixa todo o resto como está.</li>
      </ul>` },
    startover: { title: "Recomeçar de um backup (computador ou servidor novo)", body: `
      <p>O computador quebrou, foi roubado, ou você está levando o MoneyThistle para um servidor. Basta um backup: um no Nextcloud,
      ou um arquivo de backup (<code>money-…zip</code>, ou <code>.zip.enc</code> quando criptografado) e, se estiver
      criptografado, <b>a senha do backup</b>.</p>
      <ol>
        <li><b>Instale o MoneyThistle</b> no computador ou servidor novo, do mesmo jeito da primeira vez: num computador, o
          instalador (ou a pasta do MoneyThistle e <b>Start MoneyThistle</b>); num servidor, o Docker Compose ou o script de
          instalação do Unraid. Ainda não crie um acesso.</li>
        <li><b>Abra no navegador.</b> Uma instalação nova mostra <i>Configurar o MoneyThistle</i>. Embaixo, abra
          <b>Vindo de outro computador ou servidor? Começar de um backup</b>.</li>
        <li><b>Escolha o backup:</b> escolha o arquivo de backup e digite a senha, ou informe o endereço da pasta de backup do
          Nextcloud, o usuário e a senha de aplicativo, escolha <b>Mostrar seus backups</b>, escolha um (o mais recente primeiro)
          e restaure.</li>
        <li><b>Entre</b> com seu usuário e senha de sempre. Tudo voltou: cada ambiente, conta, lançamento, recibo, histórico de
          alterações e acesso.</li>
        <li><b>Confira Configurações e Backups.</b> Eles pertencem ao computador, não ao backup, então configure de novo: a conexão
          com o Nextcloud se você restaurou de um arquivo (do Nextcloud ela já vem pronta), notificações, "Outros dispositivos" e
          como o MoneyThistle inicia. A senha de backup que você digitou é mantida para os novos backups.</li>
      </ol>
      <ul>
        <li><b>Num servidor sem navegador à mão:</b> pare o MoneyThistle, depois rode
          <code>python main.py --restore money-….zip.enc</code> na pasta dele (ele pede a senha do backup) e inicie de novo.</li>
        <li><b>Já está rodando e configurado?</b> Um administrador usa <b>Backups → Restaurar de um arquivo…</b> (ou
          <b>Restaurar</b> ao lado de um backup na lista). Antes é salva uma cópia de segurança de tudo como está agora.</li>
        <li><b>Pratique uma vez:</b> restaurar num computador reserva ou num contêiner de teste é a única prova certa de que seus
          backups funcionam. <b>Verificar</b> na página Backups confere se um backup abre sem mudar nada.</li>
      </ul>` },
    simple: { title: "Simples ou Tudo", body: `
      <p>Cada pessoa escolhe quanto o MoneyThistle mostra, em <b>Configurações → Aparência</b>. Novos acessos começam no
      <b>Simples</b>.</p>
      <ul>
        <li><b>Simples</b> mostra o dia a dia. Os extras ficam recolhidos em <b>Mais opções</b> (ou <b>Mais campos</b>), prontos
          quando você quiser: número, observação e situação de um lançamento; os impostos e descontos detalhados de um holerite;
          os dados bancários, taxas e dias do cartão de uma conta; o valor variável, o lançamento automático e o último dia do mês
          de um item agendado; o horário dos backups e outros lugares para guardá-los. Mover contas entre ambientes fica de fora,
          e a lista de ambientes no topo só aparece quando há mais de um.</li>
        <li><b>Tudo</b> abre tudo.</li>
        <li>O que você abre ou fecha é lembrado para você, lugar por lugar: abra os impostos de um holerite uma vez e eles ficam
          abertos ali.</li>
        <li>Nada que afete se os seus números estão certos fica escondido, e uma seção recolhida mostra <b>● preenchido</b> quando
          algo dentro dela tem valor.</li>
      </ul>` },
    notifications: { title: "Notificações", body: `
      <p>O resumo diário lembra o que precisa de você: itens que não são automáticos, a vencer ou atrasados, em cada ambiente de
      que você participa e cada conta compartilhada com você, uma vez cada. Os automáticos (débito automático, depósito direto)
      não entram, a não ser que você marque <i>Itens automáticos a vencer também</i>: acontecem sozinhos.</p>
      <p>Configurações → Notificações envia um resumo diário (o que vence, o que foi lançado automaticamente, problemas de backup)
      por e-mail, Pushover, ntfy ou Gotify. Cada pessoa configura o seu; o e-mail pode usar as configurações compartilhadas que um
      administrador informou, ou as da própria pessoa.</p>` },
    startstop: { title: "Iniciar e parar o MoneyThistle", body: `
      <p>O MoneyThistle é um pequeno servidor; seu navegador só o mostra. <b>Fechar a aba do navegador não o para</b>, porque
      celulares e outros computadores podem estar usando. Num computador (não Docker), um administrador escolhe em
      <b>Configurações → Este computador</b>:</p>
      <ul>
        <li><b>Menu Iniciar:</b> o MoneyThistle se coloca lá na primeira vez que inicia: <b>MoneyThistle</b> abre no navegador,
          iniciando antes se não estiver rodando, e <b>Stop MoneyThistle</b> o para. Um ícone na área de trabalho é oferecido na
          instalação e nas Configurações.</li>
        <li><b>Quando eu entro neste computador:</b> ele inicia sozinho em segundo plano toda vez que você entra.</li>
        <li><b>Quando o computador ligar, mesmo que ninguém entre:</b> o Windows o inicia toda vez que o computador liga, então um
          favorito no celular sempre funciona enquanto o computador estiver ligado; você nunca precisa iniciar. Essa escolha pede
          permissão de administrador do Windows uma vez, então escolha num navegador nesse computador. Para parar, escolha uma das
          outras opções (sem permissão); o MoneyThistle continua rodando até você desligá-lo ou reiniciar o computador. No Mac ou
          no Linux, cole o comando mostrado num terminal.</li>
        <li><b>⏻ Desligar</b> (no topo da página, administradores): salva, faz o backup e para. Ninguém consegue abrir até ele ser
          iniciado de novo pelo ícone (ou o computador reiniciar, se ele inicia com o computador).</li>
        <li><b>Docker:</b> o contêiner inicia com o servidor e o mantém rodando; pare com <code>docker stop moneythistle</code>.</li>
      </ul>` },
    settings: { title: "Configurações e atualizações", body: `
      <ul>
        <li><b>Aparência:</b> claro ou escuro, cor de destaque, formato de data e o seu <b>idioma</b>: inglês, francês (Canadá),
          espanhol (América Latina) ou português (Brasil). Datas e valores seguem o estilo desse idioma. As traduções foram feitas
          por IA e ainda não foram revisadas por um falante nativo. Nomes que você digitou (contas, favorecidos, ambientes)
          aparecem sempre como estão. As categorias podem ter um nome em cada idioma (nos detalhes da categoria, em
          <i>Nome em outros idiomas</i>); as categorias iniciais já vêm com todos, e uma categoria sem ele mostra o próprio
          nome.</li>
        <li><b>Moedas:</b> cada conta tem a sua moeda (nos detalhes dela): as moedas das Américas e o euro. Uma transferência entre
          duas moedas pede o valor que realmente chegou; nenhuma cotação é buscada. Em Aparência, <b>Moedas</b> define a principal
          (totais, orçamento e relatório fiscal ficam nela) e cotações aproximadas opcionais para as outras: patrimônio líquido e
          relatórios contam as outras moedas por essas cotações, marcados como aproximados, e deixam de fora uma moeda sem cotação.
          O relatório fiscal fica na moeda principal.</li>
        <li><b>Outros dispositivos:</b> uma cópia rodando num computador só atende esse computador, a menos que você permita outros
          dispositivos da sua rede de casa (e reinicie). Os endereços para abrir estão no rodapé de cada página.</li>
        <li><b>Atualizações:</b> o MoneyThistle pergunta ao GitHub uma vez por dia se há uma versão nova (só o número
          da versão é enviado; desligue em Configurações → Este computador). No Windows, <b>Atualizar agora</b> instala e
          reinicia, ou marque <i>Instalar as versões novas sozinho</i>. No Unraid, o <i>update ready</i> da aba Docker
          atualiza o contêiner; com Docker Compose, faça pull e inicie de novo. Seus dados ficam.</li>
        <li><b>Onde estão as coisas:</b> os arquivos do app, a pasta de dados, os backups e o log aparecem em Configurações.</li>
        <li><b>Salvar:</b> uma seção com configurações para mudar tem <b>Salvar</b> e <b>Descartar alterações</b> no alto e embaixo, em cinza até algo mudar
          (enquanto isso o nome da seção ganha um ponto). Sair com alterações não salvas pergunta antes. Botões que agem na hora (Adicionar pessoa, Fazer backup agora, Enviar teste) funcionam sozinhos.</li>
      </ul>` },
    safety: { title: "Mantendo seguro", body: `
      <p><b>Nunca exponha o MoneyThistle à internet pública</b> (sem redirecionamento de porta, sem proxy reverso público).
      Use na sua rede de casa ou por uma VPN privada como o Tailscale. Ele tem login, mas não foi feito nem testado para
      resistir a ataques da internet, e ninguém pode garantir que uma cópia exposta publicamente esteja segura.</p>
      <p>Use uma senha forte para cada acesso, guarde backups em mais de um lugar e criptografe os que saem da sua casa.</p>` },
  },
  faq: [
    { q: "O MoneyThistle se conecta ao meu banco?", a: `Não. Você digita os lançamentos, ou importa um arquivo baixado do seu banco (OFX, QFX, QBO, CSV ou QIF). Nada vai para um banco nem para ninguém.` },
    { q: "Por que algo não aparece no orçamento deste mês?", a: `Confira a data: algo lançado para um mês seguinte conta naquele mês (o orçamento lista os itens lançados antes). Confira também se a categoria está no orçamento e, nas transferências, se são pagamentos (de cartão ou empréstimo) e não movimentações entre suas próprias contas.` },
    { q: "Qual a diferença entre uma conta a pagar e uma transferência?", a: `Uma conta é dinheiro saindo para outra pessoa (laranja −). Uma transferência move dinheiro entre suas próprias contas (azul ⇄); uma transferência que paga um cartão de crédito ou empréstimo conta como gasto no orçamento por itens agendados.` },
    { q: "Devo lançar cada compra no cartão ou só a fatura?", a: `Os dois jeitos funcionam. Saldo da fatura é mais rápido: um lançamento por mês. Lançar as compras dá os gastos por categoria na hora. Escolha por cartão nos Detalhes da conta; veja <a href="#/help/cards">Cartões de crédito</a>.` },
    { q: "Um lançamento se registrou sozinho. Por quê?", a: `É um item automático em Contas e depósitos com "lançar para mim" ligado. Eles aparecem marcados com ⟳ no extrato. Desligue no item se preferir lançar você mesmo.` },
    { q: "Como corrijo um erro no extrato?", a: `Clique no lançamento, escolha <b>Editar lançamento</b>, altere e escolha <b>Salvar alterações</b>. Para removê-lo, use a lixeira durante a edição.` },
    { q: "Meu cônjuge e eu podemos compartilhar contas?", a: `Sim. Dê a cada pessoa o próprio acesso (Pessoas) e depois compartilhe uma conta com o ambiente da outra pessoa, ou torne-a membro do seu. Veja <a href="#/help/people">Pessoas, ambientes e compartilhamento</a>.` },
    { q: "Posso usar no celular?", a: `Sim, no navegador do celular, na sua rede de casa ou pelo Tailscale. O Lançamento rápido (o botão +) é feito para celulares. Veja <a href="#/help/quick">Lançamento rápido</a>.` },
    { q: "Onde meus dados ficam?", a: `Na pasta de dados mostrada em Configurações → Este computador: num computador, sua própria pasta de dados de aplicativos; no Docker ou no Unraid, a pasta de dados que você mapeou. Os backups vão para onde você configurou em Configurações → Backups.` },
    { q: "Esqueci a senha de criptografia dos backups.", a: `Backups criptografados não podem ser abertos sem ela, de propósito. O seu arquivo de finanças não é afetado: defina uma nova senha em Configurações → Backups e faça um backup novo logo em seguida.` },
    { q: "Como restauro um backup?", a: `Configurações → Backups → escolha o backup → Restaurar. O MoneyThistle faz antes uma cópia de segurança do que você tem.` },
    { q: "Restaurar um backup também volta a versão antiga do MoneyThistle?", a: `Não: uma restauração traz de volta os seus dados (contas, lançamentos, recibos, pessoas), nunca o programa. O MoneyThistle que você tem continua rodando e lê os dados mais antigos. Um backup feito por um MoneyThistle <i>mais novo</i> que o seu é recusado até você atualizar, para nada se perder ou se misturar.` },
    { q: "É seguro abrir o MoneyThistle pela internet?", a: `Não: mantenha na sua rede de casa ou no Tailscale. Veja <a href="#/help/safety">Mantendo seguro</a>.` },
    { q: "Esqueci minha senha.", a: `Use <i>Esqueceu a senha?</i> na página de login, peça a um administrador, ou veja <a href="#/help/signin">Login e senhas esquecidas</a> para o caminho de volta que funciona sem e-mail.` },
    { q: "Posso trazer meu histórico do Microsoft Money ou do Quicken?", a: `Sim: cada conta, categoria e lançamento. Veja <a href="#/help/move-in">Trazer tudo de outro programa</a>.` },
    { q: "Como vejo o tour de novo?", a: `Escolha <b>Fazer o tour</b> no topo desta página de Ajuda.` },
    { q: "Como removo os dados de exemplo, ou começo do zero?", a: `Enquanto os dados de exemplo estiverem em uso, uma barra no
      topo de cada página oferece <b>Começar do zero com meu próprio dinheiro</b>. Depois, um proprietário pode começar um ambiente
      do zero em Configurações → Seus dados (digitando o nome para confirmar): saem as contas, lançamentos, a agenda, o orçamento e
      os recibos; pessoas, logins, configurações de backup e outros ambientes ficam, e uma cópia do que havia fica guardada na
      pasta de dados do MoneyThistle.` },
    { q: "Como mantenho o valor de um investimento em dia?", a: `O MoneyThistle não busca valores. Abra a conta e escolha
      <b>Atualizar valor</b>, e digite quanto vale pelo extrato ou pelo site: a diferença entra como um lançamento de
      <i>Variação de valor</i>, fora dos orçamentos e dos relatórios de gastos. Contas de investimento e aposentadoria lembram
      todo mês (junto às faturas dos cartões); desligue, ou ligue para um bem como uma casa, nos detalhes da conta.` },
    { q: "Posso ver o que um pagamento extra faria no meu empréstimo?", a: `Sim. Abra a conta do empréstimo e escolha <b>E se…</b> no cartão Empréstimo.
      Experimente um pagamento extra no principal uma vez (com o pagamento da data que escolher), um extra em cada pagamento,
      ou pagar duas vezes por mês ou a cada duas semanas em vez de mensalmente. Mostra quando seria quitado e quanto de juros
      custaria, ao lado de como está agora. Nada é salvo; pergunte ao seu credor antes de mudar a forma de pagar. Para calcular
      um empréstimo que você ainda não tem, como quanto carro um pagamento mensal pode comprar, use a <b>Calculadora de
      empréstimo</b> abaixo da lista de contas na página Contas; <b>Criar este empréstimo…</b> começa um novo a partir dela.` },
    { q: "O que é a xícara de café?", a: `O MoneyThistle é gratuito. A xícara pequena no topo e a linha no rodapé da página levam à
      página Buy Me a Coffee do autor, para quem quiser contribuir; nada é esperado, e nada é enviado para lá a menos que
      você clique. Para ocultá-las só para você, desmarque em Configurações → Aparência → Xícara de café; um administrador
      também pode ocultá-las para todos.` },
    { q: "Onde mudo a conta que paga um cartão de crédito?", a: `Em qualquer um dos dois lugares: os <b>Detalhes da conta</b> do cartão
      (Pagar com), ou o pagamento dele em <b>Contas e depósitos</b> (abra e mude a conta, o valor ou a data). Um acompanha o
      outro. Um pagamento que ficou para trás ao mover um cartão ou uma conta entre ambientes é retomado pelo cartão na próxima
      vez que os detalhes dele forem salvos: nunca fica um segundo.` },
  ],
  terms: [
    { term: "Conta", def: "Um lugar onde há dinheiro guardado ou devido: conta corrente, poupança, cartão de crédito, empréstimo, investimento." },
    { term: "Extrato", def: "A lista de lançamentos de uma conta com o saldo corrente, como um talão de cheques." },
    { term: "Lançamento", def: "Uma linha no extrato: dinheiro entrando ou saindo numa data." },
    { term: "Favorecido", def: "Para quem você pagou ou quem pagou você." },
    { term: "Categoria", def: "Para que foi o dinheiro (Supermercado, Aluguel) ou de onde veio (Salário). Categorias principais podem ter subcategorias." },
    { term: "Relacionado a impostos", def: "Uma categoria cujos lançamentos entram no relatório fiscal de fim de ano. Defina em Categorias." },
    { term: "Transferência (mover)", def: "Dinheiro passando entre duas contas suas: um lançamento em cada extrato, mantidos juntos." },
    { term: "Dividido", def: "Um pagamento feito de partes em categorias ou contas diferentes, como um pagamento de empréstimo (principal, juros, caução) ou um holerite." },
    { term: "Compensado (C)", def: "Seu banco já processou o lançamento." },
    { term: "Conciliado (R)", def: "O lançamento foi conferido com um extrato do banco em Conciliar a conta." },
    { term: "Item agendado", def: "Uma conta, depósito, transferência ou pagamento em Contas e depósitos que se repete." },
    { term: "Automático ⟳", def: "Um item agendado que acontece sozinho; com 'lançar para mim', o MoneyThistle o registra na data." },
    { term: "Saldo da fatura", def: "O que a fatura de um cartão diz que você deve na data de fechamento." },
    { term: "Dia de fechamento / vencimento", def: "O dia em que a fatura de um cartão fecha e o dia em que o pagamento vence. 31 quer dizer o último dia do mês." },
    { term: "Salário bruto", def: "Salário antes dos impostos e descontos." },
    { term: "Salário líquido", def: "O que chega na sua conta depois dos impostos e descontos." },
    { term: "Desconto antes dos impostos", def: "Tirado do salário antes do imposto de renda, como um 401(k), uma HSA pela folha ou um plano de saúde. Reduz o salário tributável (W-2 quadro 1)." },
    { term: "HSA", def: "Conta de poupança para saúde (EUA): dinheiro para despesas médicas com vantagens fiscais, até um limite anual somando todas as suas HSAs." },
    { term: "Ambiente", def: "Um grupo separado de contas (Pessoal, Empresa…) que só os membros veem." },
    { term: "Conta compartilhada", def: "Uma conta mostrada também em outro ambiente: um extrato e um saldo vistos nos dois." },
    { term: "Patrimônio líquido", def: "Tudo o que você tem menos tudo o que deve." },
    { term: "Previsão", def: "Saldos projetados a partir de hoje usando a sua agenda (Relatórios → Previsão)." },
    { term: "WebDAV", def: "Um jeito padrão de guardar arquivos num servidor; o Nextcloud usa. Serve para os backups." },
    { term: "Tailscale", def: "Uma rede privada entre os seus próprios dispositivos, para um celular longe de casa alcançar o MoneyThistle sem expô-lo à internet." },
  ],
});
