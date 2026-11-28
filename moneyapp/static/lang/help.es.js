// Ayuda de MoneyThistle en español (Latinoamérica). Traducida por IA; aún sin revisar por un hablante nativo.
"use strict";
I18N.helpText({
  guides: {
    about: { title: "Acerca de MoneyThistle", body: `
      <p><b>Por qué existe.</b> Durante años, Microsoft Money Plus Sunset fue lo último de algo bueno: un programa de finanzas
      gratuito y sin conexión que guardaba todo en tu propia computadora. Microsoft dejó de hacer Money hace mucho, y la edición
      Sunset solo envejece. MoneyThistle nació del deseo de una familia de conservar esa forma de hacer las cosas, pero más simple:
      las mismas cuentas, registros, facturas, presupuesto e informes, funcionando en casa (en una computadora, un servidor
      doméstico o en Docker), abierto en cualquier navegador de las computadoras y teléfonos de la familia, sin conexión con bancos y
      con respaldos automáticos en Nextcloud o lugares parecidos. Está pensado para que cualquiera en la familia lo pueda usar, no
      solo quien lo instaló.</p>
      <p>Se construyó después de estudiar cómo se comporta Money Plus Sunset (sus categorías, tipos de cuenta, calendarios de
      facturas y reglas de respaldo) y luego se escribió desde cero; no contiene nada de código de Microsoft.</p>
      <p><b>Cómo se hizo: "vibe coding".</b> Para ser claros desde el principio: MoneyThistle lo escribió una IA. Casi todo su
      código, sus pantallas, esta Ayuda y sus pruebas automáticas los produjo Claude, de Anthropic, a partir de pedidos en lenguaje
      sencillo. Su responsable humano decidió qué debía hacer y cómo debía sentirse, usó y probó cada función, reportó lo que
      fallaba y volvió a pedir hasta que funcionó. El responsable no ha revisado el código línea por línea.</p>
      <p><b>Qué significa para ti.</b> MoneyThistle tiene un conjunto de pruebas automáticas y uso real diario, pero no ha tenido
      revisión profesional de código ni auditoría de seguridad. Así que:</p>
      <ul>
        <li>Ten respaldos (MoneyThistle los hace solo; revisa de vez en cuando que se verifiquen).</li>
        <li>Mantenlo en tu red de casa o en Tailscale, nunca abierto al internet público.</li>
        <li>Compara los números importantes con los estados de cuenta del banco y de la tarjeta, como con cualquier programa de finanzas.</li>
        <li>Si sabes leer código: revisiones, reportes de errores y correcciones son muy bienvenidos.</li>
      </ul>
      <p><b>Software libre.</b> MoneyThistle es libre y de código abierto bajo la GNU AGPL-3.0, y viene sin ninguna garantía.
      Puedes usarlo, cambiarlo y compartirlo; una versión modificada que ofrezcas a otros, también como sitio web, debe compartir
      sus cambios. El enlace al pie de cada página descarga el código fuente exactamente de esta copia. No toma ningún dato tuyo
      ni envía nada a ningún lado, salvo a donde tú le indiques (tus respaldos y notificaciones).</p>` },
    start: { title: "Primeros pasos", body: `
      <p>MoneyThistle guarda el dinero de tu hogar en un solo lugar: cuentas y sus registros, facturas y depósitos en un calendario,
      un presupuesto mensual, informes y respaldos automáticos. No hay conexión con el banco: tú escribes los movimientos, o los
      traes de un archivo que tu banco te deja descargar.</p>
      <ol>
        <li><b>Agrega tus cuentas</b> (Cuentas → Nuevo): corriente, ahorros, tarjetas de crédito, préstamos, inversiones.
          Ingresa el saldo de cada una a una fecha y, para tarjetas y préstamos, lo que debes.</li>
        <li><b>Pon las facturas y pagos de nómina regulares en el calendario</b> (Facturas y depósitos) para que el Inicio muestre
          lo que viene y el presupuesto sepa qué esperar.</li>
        <li><b>Registra lo que pasa</b> en el registro de cada cuenta, o con <a href="#/help/quick">Agregar rápido</a>
          en tu teléfono.</li>
        <li><b>Activa los respaldos</b> (Respaldos): una carpeta y, de preferencia, también Nextcloud u otro servidor WebDAV.</li>
      </ol>
      <p>Personaliza el Inicio con <b>Personalizar</b> en la página de Inicio. Repite el recorrido cuando quieras desde esta página de Ayuda.</p>` },
    register: { title: "Las cuentas y el registro", body: `
      <p>Cada cuenta tiene un <b>registro</b>: cada movimiento con su fecha, beneficiario, categoría, monto y el saldo acumulado.
      Escribe uno nuevo en la línea de abajo: elige <b>Retiro</b> o <b>Depósito</b> y llena el beneficiario; MoneyThistle recuerda
      la categoría y el monto habituales de cada beneficiario.</p>
      <ul>
        <li><b>Cambiar un movimiento:</b> haz clic en él en el registro. Aparece en la línea de abajo, bloqueado; elige
          <b>Editar movimiento</b>, cámbialo y luego <b>Guardar cambios</b> (o <b>Cancelar</b>). El bote de basura lo elimina.</li>
        <li><b>Recibos de nómina y pagos divididos</b> se ven en una línea; <i>▸ partes</i> muestra cada parte (impuestos,
          deducciones, capital e intereses), y hacer clic en la línea lo abre. Cierra cualquier ventana con ✕, Esc o un clic
          al lado: si algo cambió, pregunta si guardar antes.</li>
        <li><b>Transferencias:</b> como categoría, elige "Transferencia a …" otra cuenta. El movimiento correspondiente se agrega
          solo a la otra cuenta.</li>
        <li><b>Movimientos divididos</b> (un pago de préstamo, un recibo de nómina) aparecen como una línea con sus partes abajo.</li>
        <li><b>Con fecha posterior a hoy:</b> los movimientos de días por venir tienen una barra a la izquierda y un fondo sombreado, para distinguir bien el pasado del futuro.</li>
        <li><b>Orden:</b> "Más recientes primero" cambia el orden. Los movimientos del mismo día se pueden mover con ▲ ▼.</li>
        <li><b>Conciliado y verificado:</b> haz clic en la columna de estado para marcar un movimiento como conciliado (C) o
          verificado (R). <b>Conciliar la cuenta</b> te guía para cuadrar un estado de cuenta.</li>
        <li><b>Detalles de la cuenta</b> guardan el banco, el número de cuenta, el sitio web, el teléfono y la tasa de interés y,
          para tarjetas, el límite y los días del estado de cuenta.</li>
        <li><b>Favoritas y orden:</b> haz clic en la ☆ junto a una cuenta de la lista para hacerla favorita (★); las favoritas van primero en su grupo.
          Para cambiar el orden, abre el 🔒 arriba de la lista, arrastra una cuenta (en el teléfono, ▲ ▼) y vuelve a cerrarlo; salir de Cuentas también lo cierra.
          Favoritas y orden son solo tuyos: cada persona que usa las mismas cuentas mantiene los suyos.</li>
        <li><b>Un pago de nómina con su recibo:</b> un clic lo muestra en la línea de abajo como cualquier movimiento, con <b>Recibos</b> (guarda ahí el PDF del recibo de nómina)
          y <b>Recibo de nómina</b>, que lo abre. La etiqueta verde <b>Recibo de nómina</b> en la línea lo abre directamente.</li>
      </ul>` },
    balances: { title: "Saldo y saldo compensado", body: `
      <p>Cada cuenta muestra dos totales lado a lado.</p>
      <ul>
        <li>El <b>saldo</b> cuenta todo lo anotado en el registro: cada movimiento, compensado o no, incluso los fechados después de hoy.</li>
        <li>El <b>saldo compensado</b> cuenta solo los movimientos marcados como compensados (C) o conciliados (R): lo que el banco ya vio. Es el que se compara con el saldo del banco.</li>
        <li><b>Por qué difieren:</b> cheques aún no cobrados, cargos de tarjeta pendientes, depósitos aún no acreditados y movimientos con fecha futura cuentan en el saldo, pero no en el compensado.</li>
        <li><b>Cuándo revisar:</b> una diferencia que va y viene es normal. Una que no deja de crecer, o movimientos de hace semanas aún sin compensar, suele indicar algo que nunca llegó al banco o que se anotó dos veces.
          <b>Conciliar la cuenta</b> recorre un estado de cuenta y marca lo que coincide. Una cuenta nunca conciliada muestra una gran diferencia solo porque aún no hay nada marcado.</li>
      </ul>` },
    cards: { title: "Tarjetas de crédito", body: `
      <p>Cada tarjeta se lleva de una de dos formas (Detalles de la cuenta → <i>¿Cómo llevas esta tarjeta?</i>):</p>
      <ul>
        <li><b>Saldo del estado de cuenta:</b> una vez al mes ingresas el saldo del estado de cuenta; un movimiento deja la tarjeta
          en lo que debe. Con el día de corte lleno, el Inicio te recuerda cuando un estado de cuenta ha cerrado.</li>
        <li><b>Cada compra:</b> registras cada cargo. El presupuesto por elementos programados muestra los cargos del mes como
          pendientes, que se pagan después con el pago de la tarjeta, para que nada cuente dos veces.</li>
      </ul>
      <p><b>Pagar una tarjeta:</b> una transferencia de la cuenta corriente a la tarjeta. Un botón ofrece el saldo del último estado
      de cuenta (menos lo pagado desde entonces). Marca <i>Mantener el pago de la tarjeta en mi calendario</i> para tener el pago en
      Facturas y depósitos cada mes en el día de pago.</p>
      <p><b>Una tarjeta para un solo tipo de gasto</b> (gastos elegibles de HSA, donativos, un negocio): elígelo en
      <i>¿Para qué se usa esta tarjeta?</i>. Sus cargos y estados de cuenta van solos a esa categoría.</p>
      <p><b>Último día del mes:</b> ingresa 31 como día de corte o de pago. Los meses más cortos usan su último día;
      29 y 30 funcionan igual en febrero.</p>` },
    receipts: { title: "Recibos y otros archivos", body: `
      <p>Guarda una foto del recibo, o un PDF (una factura, una garantía, una cuenta médica para tu HSA), con el movimiento al que
      pertenece.</p>
      <ul>
        <li><b>En un teléfono:</b> debajo de un movimiento nuevo, <b>📷 Tomar una foto</b> abre la cámara; la foto se adjunta al
          presionar Registrar. <b>Elegir una foto o archivo</b> toma uno que ya tienes.</li>
        <li><b>Después:</b> elige el movimiento en el registro y luego <b>Recibos</b> para agregar más, abrirlos, descargarlos o
          quitarlos. Los movimientos con algo adjunto muestran un clip.</li>
        <li><b>Documentos guardados con una cuenta:</b> en una tarjeta en la que solo registras estados de cuenta y pagos, no hay
          movimiento para la TV que compraste. Elige <b>Documentos</b> en la página de la cuenta para guardar el recibo, la garantía
          o el contrato con la cuenta misma, con la fecha a la que corresponde.</li>
        <li><b>Notas y palabras clave:</b> ponle a cualquier archivo una nota corta ("TV, garantía 2 años, serie 12345") al
          agregarlo, o después debajo de él. Todo lo que escribes se guarda al salir del campo.</li>
        <li><b>Archivos</b> (en el menú) lista cada recibo y documento de este entorno, los más recientes primero. Busca por
          cualquier palabra de la nota, el nombre del archivo, el beneficiario o la cuenta; limítalo a una cuenta o un periodo;
          haz clic en una columna para ordenar.</li>
        <li>Las fotos se reducen antes de enviarse (unos 400 KB en lugar de varios MB); un PDF puede pesar hasta 20 MB.</li>
        <li>Los archivos se guardan en la carpeta de datos y van en cada respaldo, incluido Nextcloud.</li>
        <li>Eliminar un movimiento aparta sus archivos por 60 días, así que deshacer la eliminación (Historial) los recupera.</li>
      </ul>` },
    paystubs: { title: "Pagos de nómina y recibos", body: `
      <p>Registra un pago de nómina con lo que sepas. El <b>sueldo neto</b> (lo que llegó a tu banco) es suficiente; el sueldo bruto
      y las deducciones del recibo pueden venir ahora o después. En la cuenta a la que llega el pago, elige <b>Recibo de nómina…</b>
      arriba de la línea de registro. Solo el sueldo neto es obligatorio.</p>
      <ul>
        <li><b>Otras deducciones:</b> cuando agregas el sueldo bruto, lo que no esté detallado (bruto menos neto menos las
          deducciones que escribiste) se muestra y se guarda como <b>Otras deducciones</b>. Detalla tanto o tan poco como quieras;
          en 0 todo está detallado. Si las deducciones suman más que el bruto menos el neto, el recibo no se puede guardar hasta
          que los montos cuadren.</li>
        <li><b>Agregado después de impuestos:</b> dinero en el sueldo neto que no es sueldo (un reembolso de gastos, una devolución).
          Agrégalo en <b>+ Algo agregado después de impuestos</b> para que no oculte una deducción.</li>
        <li><b>Pagos de nómina programados:</b> en Facturas y depósitos, marca <b>Es un pago de nómina</b> en el depósito (su monto
          es el sueldo neto, o su promedio). Cuando vence, <b>Registrar</b> ofrece <b>Registrar solo el sueldo neto</b> o
          <b>Llenar el recibo de nómina</b>.</li>
        <li><b>Agregar detalles después:</b> un pago registrado solo con su sueldo neto aparece marcado como <b>Pago de nómina</b>
          en el registro; ábrelo y elige <b>Agregar detalles del recibo de nómina</b>.</li>
        <li><b>Lo que falta se marca:</b> MoneyThistle aprende lo habitual de cada empleador (solo neto, bruto y neto, o cada
          impuesto y deducción) a partir de sus últimos pagos. Un pago con menos de lo habitual muestra <b>⚑</b> en el registro
          (<i>falta el sueldo bruto</i>, <i>falta: Medicare</i>, o <i>$220.00 sin detallar</i> cuando los recibos de ese empleador
          suelen estar totalmente detallados), y el informe fiscal de fin de año los lista en <b>Pagos de nómina por revisar</b>.
          Si bruto y neto es lo habitual, Otras deducciones nunca se marcan; si solo neto es lo habitual, nada se marca.
          <b>Completo así</b> deja de marcar uno que no tendrá más detalle.</li>
        <li>Cada impuesto o deducción va a una categoría (Impuesto federal sobre la renta, Seguros : Salud…) o a una de tus cuentas
          (un 401(k), una HSA), donde aparece como dinero que entra. ¿No llevas esa cuenta en MoneyThistle? Usa <b>Ahorros e inversiones</b>
          (Plan de jubilación, Cuenta de salud) en su lugar. Cada recibo nuevo empieza como copia del anterior;
          mueve las líneas con ▲ ▼ (o Alt+↑ ↓) para seguir el orden de tu recibo.</li>
        <li><b>Pago depositado en más de una cuenta</b> ($250 a ahorros, $3,210.14 a cheques): en <i>Depositado en</i>,
          elige <i>+ Agregar una cuenta</i> e ingresa lo que llegó a cada una. El pago neto es su total. También funciona
          solo con el pago neto. El monto de un pago programado puede ser el total o lo que llega a su propia cuenta. Un depósito programado también puede tener varias cuentas (Facturas y depósitos, <i>+ Agregar una cuenta</i>), cada
          una con un monto fijo o el promedio de lo que recibió antes; se registran juntas.</li>
        <li>En el presupuesto, un pago de nómina cuenta por su sueldo neto. Los informes muestran cada línea, y el informe fiscal
          de fin de año muestra bruto vs neto de cada empleador.</li>
      </ul>` },
    bills: { title: "Facturas y depósitos (el calendario)", body: `
      <p>Todo lo que se repite: facturas, pagos de nómina, transferencias a ahorros, pagos de préstamo y de tarjeta. Cada elemento
      tiene una cuenta, un monto y una frecuencia, de diaria a anual (o solo una vez). Un elemento mensual puede caer el
      <b>último día del mes</b>.</p>
      <ul>
        <li><b>Registrar</b> anota el siguiente en el registro (puedes cambiar antes el monto y la fecha); <b>Omitir</b> se salta
          uno que no pasó. Puede ir con un recibo, estado de cuenta o recibo de nómina: elige <b>Agregar un recibo o archivo</b>
          (o <b>Tomar una foto</b> en un teléfono) antes de registrar.</li>
        <li><b>Monto variable:</b> el calendario espera el promedio de los últimos registrados.</li>
        <li><b>Automático ⟳:</b> marca los elementos que pasan solos (pago automático, depósito directo). Elige
          <i>registrarlo por mí</i> y MoneyThistle registra cada uno en su fecha, marcado con ⟳ en el registro.</li>
        <li>El Inicio lista lo que vence pronto; Informes → Lo que viene usa el calendario para pronosticar saldos.</li>
        <li><b>Próximamente</b> muestra cada vez que un elemento ocurre en los días elegidos. Solo el primero se puede registrar u omitir; los siguientes muestran lo que viene.
          La cuenta con más movimientos va primero, y las tarjetas llenan las columnas para que una larga no deje un hueco al lado.</li>
        <li><b>Mostrar automáticos</b> (marcado) incluye también lo automático; desmárcalo para ver solo lo que necesita tu atención. Tu elección se recuerda en todos tus dispositivos.</li>
        <li><b>Pagar esta factura ↗</b> abre el sitio donde se paga: escríbelo en <i>Más opciones</i> (<i>Sitio para pagarla</i>). Los pagos de tarjeta y de préstamo usan el sitio de los detalles de la tarjeta o del préstamo.
          Los depósitos y transferencias tienen <b>Ver cuenta ↗</b>, al sitio de la cuenta.</li>
        <li><b>Un promedio:</b> haz clic en el monto promedio de un elemento programado para ver los montos de los que sale, con sus fechas.</li>
      </ul>
      <p>Colores y símbolos: el dinero que entra es verde <b>+</b>, el que sale es naranja <b>−</b>, los movimientos entre tus
      propias cuentas son azules <b>⇄</b>.</p>` },
    budget: { title: "El presupuesto", body: `
      <p>Dos estilos; cambia con los botones arriba en la página Presupuesto:</p>
      <ul>
        <li><b>Por categoría:</b> cada categoría del presupuesto tiene un monto mensual. Deja una en 0 y espera lo que tu
          calendario tenga para ella ese mes. Los gastos se muestran en cada línea conforme ocurren.</li>
        <li><b>Por elementos programados:</b> para quien no lleva categorías. Cada factura, depósito y transferencia del calendario
          es una línea: lo esperado este mes y lo ya registrado.</li>
      </ul>
      <p>Los pagos de préstamo cuentan completos (capital, intereses y depósito en garantía juntos). Los recibos de nómina cuentan
      por su sueldo neto. Algo registrado antes con fecha del mes siguiente cuenta en el mes siguiente; el presupuesto lo señala.</p>` },
    reports: { title: "Informes", body: `
      <ul>
        <li><b>A dónde va / de dónde viene el dinero:</b> totales por categoría en un periodo. Haz clic en una para ver sus movimientos.</li>
        <li><b>Ingresos vs. gastos:</b> mes a mes durante el último año.</li>
        <li><b>Patrimonio neto en el tiempo:</b> todo lo que tienes menos todo lo que debes, mes a mes.</li>
        <li><b>Lo que viene:</b> el saldo de cada cuenta día a día desde hoy, usando tu calendario. Marca cuentas para dibujarlas;
          haz clic en un elemento programado para marcar su día.</li>
        <li><b>Impuestos:</b> ver <a href="#/help/taxes">el informe fiscal de fin de año</a>.</li>
      </ul>
      <p>Se incluyen las cuentas compartidas con este entorno.</p>` },
    taxes: { title: "El informe fiscal de fin de año", body: `
      <p>Informes → <b>Impuestos</b> reúne todo lo que está en categorías marcadas como <b>Relacionado con impuestos</b> (se define
      en Categorías) de un año calendario, con cada movimiento listado: ingresos y luego deducciones y gastos. Descárgalo como hoja
      de cálculo o imprímelo (o guárdalo como PDF) para tu contador.</p>
      <ul>
        <li><b>Sueldo:</b> con recibos de nómina registrados, bruto vs neto de cada empleador y cada impuesto y deducción.
          No hay que escribir el W-2: compara estos totales con el W-2 que envía tu empleador.</li>
        <li><b>Cuentas de ahorro para la salud (HSA):</b> marca una cuenta como HSA en sus detalles e indica quién deposita.
          El informe suma tus aportaciones después de impuestos (deducibles) y las de antes de impuestos (del empleador o la
          nómina, en tu W-2) en <i>todas</i> tus HSA, las compara con el límite anual que ingresas y lista los retiros. Tus propias
          aportaciones hechas del 1 de enero al 15 de abril pueden contar para el año anterior.</li>
        <li><b>Otras monedas:</b> el informe se queda en la moneda principal; las cuentas en otras monedas se listan para que sumes
          esos montos con los tipos de cambio oficiales.</li>
      </ul>
      <p>Es un resumen para comparar con tus formularios fiscales, no asesoría fiscal.</p>` },
    import: { title: "Importar desde tu banco", body: `
      <p>En el registro de una cuenta, elige <b>Importar archivo</b> y un archivo descargado del sitio de tu banco:
      <b>OFX, QFX o QBO</b> (lo mejor: traen los identificadores del propio banco), <b>CSV</b> (una hoja de cálculo con columnas
      Fecha y Monto, o Débito/Crédito) o <b>QIF</b>.</p>
      <p>Antes de agregar algo ves una revisión: los movimientos que coinciden con uno que ya tienes (mismo monto en pocos días) se
      emparejan en vez de duplicarse; los duplicados exactos se omiten; tú decides el resto. Importar el mismo archivo OFX dos veces
      no agrega nada.</p>` },
    "move-in": { title: "Mudarse desde otro programa", body: `
      <p>Configuración → <b>Traer todo desde otro programa…</b> trae cada cuenta y su historial de una vez.</p>
      <ul>
        <li><b>Microsoft Money:</b> Archivo → Exportar, una vez por cuenta (Loose QIF sirve). Elige todos los archivos juntos;
          cada cuenta toma su nombre real del saldo inicial, y las transferencias entre ellas se emparejan.</li>
        <li><b>Quicken, Moneydance, KMyMoney, HomeBank, Money Manager Ex, Banktivity:</b> exporta todo a un archivo QIF.</li>
        <li><b>YNAB, GnuCash, Actual Budget, Mint, Firefly III:</b> su exportación CSV de todas las transacciones. Cualquier otro CSV
          sirve si tiene columnas Cuenta, Fecha, Beneficiario, Categoría y Monto.</li>
      </ul>
      <p>Primero ves lo que hay en el archivo: cada cuenta con sus movimientos, fechas y saldo, y las categorías que agregaría.
      Para cada cuenta elige una cuenta nueva, una que ya tienes, o dejarla fuera. Nada cambia hasta <b>Importarlo</b>.</p>
      <p>Viene: cuentas, saldos iniciales, categorías, beneficiarios y cada transacción con sus divisiones, transferencias y marcas
      de conciliado. No viene: facturas programadas, presupuestos y posiciones de inversión. Los movimientos que ya están en una
      cuenta que eliges no se agregan dos veces. Haz un respaldo antes; la descarga del banco de una sola cuenta sigue pasando por
      <a href="#/help/import">Importar archivo</a>.</p>
      <p>Para volver a armar tu calendario, abre un registro y haz clic en una factura, un sueldo o una transferencia que se repite, y luego
      en <b>Programar…</b>. Se llena un nuevo elemento programado a partir de ese movimiento: el beneficiario, la cuenta, la categoría y
      el monto, y la frecuencia y la próxima fecha según los otros movimientos del mismo beneficiario en esa cuenta (un monto que
      cambia queda como variable, por su promedio). Revísalo y guárdalo.</p>
      <p>Un préstamo o hipoteca llega como una simple cuenta de préstamo, sin su tasa ni su pago. Ábrela y elige
      <b>Configurar los detalles del préstamo…</b>: se completan a partir de sus pagos (revísalos con un estado de cuenta), y
      entonces tiene su calendario de pagos, la fecha en que queda pagado y <b>¿Y si…?</b>. Su registro y su saldo quedan como están.</p>` },
    history: { title: "Historial de cambios y deshacer", body: `
      <p>MoneyThistle registra cada movimiento, elemento programado, cuenta, categoría y monto del presupuesto que se agrega,
      cambia o elimina: quién lo hizo, cuándo, en qué entorno y cómo estaba antes y después. Se guarda un año y va en cada respaldo.</p>
      <ul>
        <li><b>Todo:</b> Personas → <b>Historial de cambios</b> (o Configuración → Tus datos). Filtra por entorno o persona, o busca.</li>
        <li><b>Un movimiento:</b> haz clic en él en el registro y luego en <b>Historial</b>.</li>
        <li><b>Deshacer:</b> los cambios en movimientos y elementos programados los puede deshacer cualquiera que pueda cambiar ese
          entorno: un movimiento agregado se va, uno cambiado vuelve a como estaba, uno eliminado regresa (una transferencia con sus
          dos lados). Si se cambió otra vez después, deshaz primero el cambio más reciente. Para lo demás, restaura un respaldo.</li>
      </ul>` },
    allenvs: { title: "Ver varios entornos juntos", body: `
      <p>Con cuentas en más de un entorno (las privadas en uno, las del hogar en otro), Inicio, Cuentas, Facturas y depósitos,
      Presupuesto e Informes tienen un selector de <b>Entornos</b> arriba. Marca los que quieras ver juntos, por ejemplo el personal
      y el del hogar pero no el del negocio. El entorno en que estás siempre se incluye. <b>Todos</b> marca cada uno; <b>Solo</b>
      seguido del nombre actual desmarca el resto. La elección es la misma en cada página y se recuerda en este navegador.</p>
      <ul>
        <li>Todo se suma entre los entornos marcados; cada elemento muestra en cuál está. Una cuenta compartida entre dos de ellos
          cuenta una vez, y las transferencias entre ellos no son gastos.</li>
        <li>Los cambios se siguen haciendo en el entorno propio de cada elemento: registrar una factura, abrir una cuenta o un estado
          de cuenta de otro entorno cambia a ese entorno.</li>
        <li>El presupuesto combinado es para ver: las líneas con la misma categoría se suman. Los montos del presupuesto se definen
          en cada entorno.</li>
      </ul>` },
    signin: { title: "Inicio de sesión y contraseñas olvidadas", body: `
      <p>Cada persona tiene su propio acceso. Cambia tu nombre, correo o contraseña en <b>Personas → Tu acceso</b>.</p>
      <ul>
        <li><b>Mantener la sesión en este dispositivo:</b> si lo marcas al entrar, sigues dentro 30 días, también después de
          reiniciar la computadora. Sin marcar (mejor en dispositivos compartidos), la sesión se cierra al cerrar el navegador, o
          tras una hora sin uso. <b>Cerrar sesión</b> la termina de inmediato.</li>
        <li><b>¿Olvidaste tu contraseña?</b> En la página de inicio de sesión elige <i>¿Olvidaste tu contraseña?</i>. Si tu acceso
          tiene correo y un administrador configuró el correo (Configuración → Notificaciones), MoneyThistle te envía un enlace
          para elegir una nueva. El enlace sirve una vez, por 30 minutos, desde tu red de casa o Tailscale.</li>
        <li><b>¿Sin correo?</b> Cualquier administrador puede ponerte una contraseña nueva en Personas.</li>
        <li><b>El único administrador, sin acceso:</b> en la computadora o servidor donde corre MoneyThistle, ejecuta
          <code>python main.py --reset-password TU-USUARIO</code> en su carpeta (con Docker:
          <code>docker exec -it moneythistle python main.py --reset-password TU-USUARIO</code>).
          <code>--list-users</code> muestra los nombres de usuario.</li>
      </ul>
      <p>Cada vez que cambia una contraseña, todos los dispositivos que la usan cierran sesión, y la persona recibe un correo avisando (si tiene dirección).</p>` },
    quick: { title: "Agregar rápido en tu teléfono", body: `
      <p>En un teléfono, el botón redondo <b>+</b> (o la dirección <code>#/quick</code>) abre una pantalla hecha para un pulgar:
      elige dinero que sale, que entra o un movimiento entre cuentas, escribe el monto, el beneficiario y la cuenta, y guarda.
      Lo que vence hoy también se puede registrar desde ahí.</p>
      <p>Agrega MoneyThistle a la pantalla de inicio del teléfono (en el menú de compartir o del navegador: <i>Agregar a la
      pantalla de inicio</i>) y se abre como una app. El teléfono necesita alcanzar MoneyThistle: en tu red de casa, o por Tailscale.</p>` },
    people: { title: "Personas, entornos y compartir", body: `
      <ul>
        <li><b>Personas:</b> cada quien entra con su propio usuario y contraseña. Los administradores agregan accesos y restablecen
          contraseñas.</li>
        <li><b>Correo de bienvenida:</b> con el correo configurado (Configuración › Notificaciones), al agregar a alguien se le puede enviar una bienvenida:
          quién lo agregó, su nombre de usuario, las direcciones para abrir MoneyThistle, qué puede ver y un enlace para elegir su
          propia contraseña (funciona una vez, durante 3 días). <b>Enviar bienvenida</b> en la lista la vuelve a enviar.</li>
        <li><b>Una tarjeta pagada desde otro entorno:</b> en los detalles de una tarjeta, <b>Pagar desde</b> también muestra cuentas
          de otros entornos que son tuyos. El pago se guarda donde sale el dinero (por ejemplo la cuenta corriente de Household),
          conectado solo, y también se ve en Facturas y depósitos y en el Inicio de la tarjeta.</li>
        <li><b>Entornos</b> son grupos de cuentas separados (Personal, Negocio, Suegros…). Solo sus miembros los ven. Los dueños
          agregan miembros como dueño, editor (puede cambiar cosas) o lector (solo mira). Cambia arriba a la derecha.</li>
        <li><b>Cuentas compartidas:</b> muestra una cuenta también en otro entorno (tu cuenta corriente en el entorno de tu pareja):
          un registro, un saldo, visto en ambos, opcionalmente con sus facturas y depósitos.</li>
        <li><b>Conexiones</b> te dejan mover dinero entre entornos: "Transferencia a …" llena el otro lado.</li>
        <li><b>Mover cuentas:</b> para darles un nuevo hogar a unas cuentas (por ejemplo, de tu entorno Personal a uno del hogar que
          comparten), abre la cuenta, elige <b>Detalles de la cuenta → Mover a otro entorno…</b>, marca todas las cuentas que se van
          juntas y revisa qué pasará antes. Todo se va con ellas: movimientos, elementos programados, categorías y beneficiarios.
          Las transferencias a cuentas que se quedan se vuelven transferencias entre entornos. Primero se hace un respaldo.</li>
      </ul>` },
    backups: { title: "Respaldos", body: `
      <p>MoneyThistle respalda solo: después de cambios y con un horario. Cada respaldo guarda todo: todos los entornos y accesos.</p>
      <ul>
        <li><b>Dónde:</b> una carpeta, y Nextcloud o cualquier servidor WebDAV (usa una <i>contraseña de aplicación</i> de
          Nextcloud). La carpeta de respaldos allí se crea si no existe.</li>
        <li><b>Verificado:</b> después de cada envío la copia se descarga de nuevo y se compara; una copia dañada se elimina.
          <b>Verificar</b> revisa cualquier respaldo cuando lo pidas.</li>
        <li><b>Cifrado:</b> con una contraseña de respaldo, los respaldos no se pueden leer sin ella. Guárdala bien:
          <b>una contraseña perdida no se puede recuperar</b>, ni sus respaldos.</li>
        <li><b>Hasta cuándo:</b> los pocos respaldos más recientes tras cambios, más el último respaldo de cada uno de los últimos
          7 días, 4 semanas y 12 meses. Un día con muchos cambios no saca el respaldo de ayer, así que un error que encuentres
          después todavía se puede deshacer. Las copias de <b>Respaldar ahora</b> se conservan hasta que las elimines. La lista
          dice por qué se guarda cada una.</li>
        <li><b>Restaura</b> cualquier respaldo desde la página Respaldos. Todo vuelve a como estaba entonces (primero se hace una
          copia de seguridad de lo actual). Para un movimiento o elemento programado cambiado por error,
          <b>Historial de cambios → Deshacer</b> es más rápido y deja todo lo demás igual.</li>
      </ul>` },
    startover: { title: "Empezar desde un respaldo (computadora o servidor nuevo)", body: `
      <p>La computadora murió, la robaron, o estás pasando MoneyThistle a un servidor. Solo necesitas un respaldo: uno en Nextcloud,
      o un archivo de respaldo (<code>money-…zip</code>, o <code>.zip.enc</code> si está cifrado) y, si está cifrado,
      <b>su contraseña de respaldo</b>.</p>
      <ol>
        <li><b>Instala MoneyThistle</b> en la computadora o servidor nuevo, igual que la primera vez: en una computadora, el
          instalador (o la carpeta de MoneyThistle y <b>Start MoneyThistle</b>); en un servidor, Docker Compose o el script de
          instalación de Unraid. Todavía no crees un acceso.</li>
        <li><b>Ábrelo en el navegador.</b> Una instalación nueva muestra <i>Configurar MoneyThistle</i>. Debajo, abre
          <b>¿Vienes de otra computadora o servidor? Empezar desde un respaldo</b>.</li>
        <li><b>Elige el respaldo:</b> elige el archivo de respaldo y escribe su contraseña, o ingresa la dirección de tu carpeta de
          respaldos en Nextcloud, el usuario y la contraseña de aplicación, elige <b>Mostrar sus respaldos</b>, elige uno (el más
          reciente primero) y restáuralo.</li>
        <li><b>Inicia sesión</b> con tu usuario y contraseña de siempre. Todo regresó: cada entorno, cuenta, movimiento, recibo,
          historial de cambios y acceso.</li>
        <li><b>Revisa Configuración y Respaldos.</b> Estos pertenecen a la computadora, no al respaldo, así que configúralos de
          nuevo: la conexión con Nextcloud si restauraste desde un archivo (desde Nextcloud queda lista), las notificaciones,
          "Otros dispositivos" y cómo inicia MoneyThistle. La contraseña de respaldo que escribiste se conserva para los nuevos
          respaldos.</li>
      </ol>
      <ul>
        <li><b>En un servidor sin navegador a la mano:</b> detén MoneyThistle, luego ejecuta
          <code>python main.py --restore money-….zip.enc</code> en su carpeta (pide la contraseña del respaldo) e inícialo de nuevo.</li>
        <li><b>¿Ya está funcionando y configurado?</b> Un administrador usa <b>Respaldos → Restaurar desde un archivo…</b> (o
          <b>Restaurar</b> junto a un respaldo de la lista). Primero se guarda una copia de seguridad de todo como está ahora.</li>
        <li><b>Practica una vez:</b> restaurar en una computadora de repuesto o un contenedor de prueba es la única prueba segura de
          que tus respaldos funcionan. <b>Verificar</b> en la página Respaldos revisa que un respaldo abra sin cambiar nada.</li>
      </ul>` },
    simple: { title: "Simple o Todo", body: `
      <p>Cada persona elige cuánto le muestra MoneyThistle, en <b>Configuración → Apariencia</b>. Los accesos nuevos empiezan en
      <b>Simple</b>.</p>
      <ul>
        <li><b>Simple</b> muestra lo de todos los días. Los extras quedan plegados en <b>Más opciones</b> (o <b>Más campos</b>),
          listos cuando los quieras: el número, la nota y el estado de un movimiento; los impuestos y deducciones separados de un
          recibo de nómina; los datos bancarios, tasas y días de tarjeta de una cuenta; el monto variable, el registro automático y
          el último día del mes de un elemento programado; el horario de los respaldos y otros lugares para guardarlos. Mover
          cuentas entre entornos queda fuera, y la lista de entornos arriba solo aparece si hay más de uno.</li>
        <li><b>Todo</b> abre todo.</li>
        <li>Lo que abres o cierras se recuerda para ti, lugar por lugar: abre una vez los impuestos de un recibo y ahí se quedan abiertos.</li>
        <li>Nunca se oculta nada que afecte si tus números están bien, y una sección plegada dice <b>● con datos</b> cuando algo
          dentro tiene un valor.</li>
      </ul>` },
    notifications: { title: "Notificaciones", body: `
      <p>El resumen diario te recuerda lo que necesita tu atención: lo que no es automático y está por vencer o atrasado, en cada
      entorno al que perteneces y cada cuenta compartida contigo, una vez cada uno. Lo automático (débitos automáticos, depósitos
      directos) no aparece, salvo que marques <i>También lo automático por vencer</i>: ocurre solo.</p>
      <p>Configuración → Notificaciones envía un resumen diario (lo que vence, lo que se registró automáticamente, problemas de
      respaldo) por correo, Pushover, ntfy o Gotify. Cada persona configura el suyo; el correo puede usar la configuración
      compartida que ingresó un administrador, o la propia.</p>` },
    startstop: { title: "Iniciar y detener MoneyThistle", body: `
      <p>MoneyThistle es un pequeño servidor; tu navegador solo lo muestra. <b>Cerrar la pestaña del navegador no lo detiene</b>,
      porque teléfonos y otras computadoras pueden estar usándolo. En una computadora (no Docker), un administrador elige en
      <b>Configuración → Esta computadora</b>:</p>
      <ul>
        <li><b>Menú Inicio:</b> MoneyThistle se coloca ahí la primera vez que inicia: <b>MoneyThistle</b> lo abre en el navegador,
          iniciándolo antes si no está corriendo, y <b>Stop MoneyThistle</b> lo detiene. Se ofrece un ícono en el escritorio al
          instalarlo y en Configuración.</li>
        <li><b>Cuando inicio sesión en esta computadora:</b> se inicia solo en segundo plano cada vez que inicias sesión.</li>
        <li><b>Al encender la computadora, aunque nadie inicie sesión:</b> Windows lo inicia cada vez que se enciende la
          computadora, así que un marcador en tu teléfono siempre funciona mientras la computadora esté encendida; nunca lo inicias
          tú. Elegirlo pide permiso de administrador de Windows una vez, así que elígelo en un navegador en esa computadora. Para
          quitarlo, elige otra opción (sin permiso); MoneyThistle sigue corriendo hasta que lo apagues o reinicies la computadora.
          En Mac o Linux, pega el comando que aparece en una terminal.</li>
        <li><b>⏻ Apagar</b> (arriba en la página, administradores): guarda, hace su respaldo y se detiene. Nadie puede abrirlo hasta
          que se inicie de nuevo desde su ícono (o se reinicie la computadora, si inicia con la computadora).</li>
        <li><b>Docker:</b> el contenedor inicia con el servidor y lo mantiene corriendo; detenlo con <code>docker stop moneythistle</code>.</li>
      </ul>` },
    settings: { title: "Configuración y actualizaciones", body: `
      <ul>
        <li><b>Apariencia:</b> claro u oscuro, color de acento, formato de fecha y tu <b>idioma</b>: inglés, francés (Canadá),
          español (Latinoamérica) o portugués (Brasil). Las fechas y montos siguen el estilo de ese idioma. Las traducciones las
          hizo una IA y aún no las revisa un hablante nativo. Los nombres que escribiste (cuentas, beneficiarios, entornos)
          siempre aparecen tal cual. Las categorías pueden tener un nombre en cada idioma (en los detalles de la categoría,
          en <i>Nombre en otros idiomas</i>); las categorías iniciales ya los traen todos, y una categoría sin él muestra su
          propio nombre.</li>
        <li><b>Monedas:</b> cada cuenta tiene su propia moneda (en sus detalles): las monedas de las Américas y el euro. Una
          transferencia entre dos monedas pide el monto que realmente llegó; no se busca ningún tipo de cambio. En Apariencia,
          <b>Monedas</b> define la principal (totales, presupuesto e informe fiscal están en ella) y tipos de cambio aproximados
          opcionales para las demás: el patrimonio neto y los informes cuentan las otras monedas a esos tipos, marcados como
          aproximados, y dejan fuera una moneda sin tipo de cambio. El informe fiscal se queda en la moneda principal.</li>
        <li><b>Otros dispositivos:</b> una copia que corre en una computadora solo atiende a esa computadora, a menos que permitas
          otros dispositivos de tu red de casa (y reinicies). Las direcciones para abrirlo están al pie de cada página.</li>
        <li><b>Actualizaciones:</b> MoneyThistle le pregunta a GitHub una vez al día si hay una versión nueva (solo se
          envía su número de versión; apágalo en Configuración → Esta computadora). En Windows, <b>Actualizar ahora</b> la
          instala y reinicia, o marca <i>Instalar las versiones nuevas por sí solo</i>. En Unraid, el <i>update ready</i>
          de la pestaña Docker actualiza el contenedor; con Docker Compose, haz pull y vuelve a iniciarlo. Tus datos se quedan.</li>
        <li><b>Dónde están las cosas:</b> los archivos de la app, la carpeta de datos, los respaldos y el registro aparecen en Configuración.</li>
        <li><b>Guardar:</b> una sección con ajustes para cambiar tiene <b>Guardar</b> y <b>Descartar cambios</b> arriba y abajo, en gris hasta que algo cambie
          (mientras tanto el nombre de la sección lleva un punto). Salir con cambios sin guardar pregunta primero. Los botones que actúan de inmediato (Agregar persona, Respaldar ahora, Enviar prueba) funcionan por su cuenta.</li>
      </ul>` },
    safety: { title: "Mantenerlo seguro", body: `
      <p><b>Nunca expongas MoneyThistle al internet público</b> (sin reenvío de puertos, sin proxy inverso público).
      Úsalo en tu red de casa o a través de una VPN privada como Tailscale. Tiene inicio de sesión, pero no está hecho ni probado
      para resistir ataques desde internet, y nadie puede garantizar que una copia expuesta públicamente sea segura.</p>
      <p>Usa una contraseña fuerte para cada acceso, guarda respaldos en más de un lugar y cifra los que salen de tu casa.</p>` },
  },
  faq: [
    { q: "¿MoneyThistle se conecta a mi banco?", a: `No. Tú escribes los movimientos, o importas un archivo que descargaste de tu banco (OFX, QFX, QBO, CSV o QIF). Nada va a un banco ni a nadie más.` },
    { q: "¿Por qué algo no aparece en el presupuesto de este mes?", a: `Revisa su fecha: algo registrado para un mes posterior cuenta en ese mes (el presupuesto lista lo registrado por adelantado). Revisa también que su categoría esté en el presupuesto y, en las transferencias, que sean pagos (a una tarjeta o préstamo) y no movimientos entre tus propias cuentas.` },
    { q: "¿Cuál es la diferencia entre una factura y una transferencia?", a: `Una factura es dinero que sale hacia alguien más (naranja −). Una transferencia mueve dinero entre tus propias cuentas (azul ⇄); una transferencia que paga una tarjeta de crédito o un préstamo cuenta como gasto en el presupuesto por elementos programados.` },
    { q: "¿Registro cada compra con tarjeta o solo el estado de cuenta?", a: `Las dos formas sirven. El saldo del estado de cuenta es más rápido: un movimiento al mes. Registrar las compras te da los gastos por categoría al momento. Elige por tarjeta en sus Detalles de la cuenta; ver <a href="#/help/cards">Tarjetas de crédito</a>.` },
    { q: "Un movimiento se registró solo. ¿Por qué?", a: `Es un elemento automático en Facturas y depósitos con "registrarlo por mí" activado. Esos aparecen marcados con ⟳ en el registro. Desactívalo en el elemento si prefieres registrarlo tú.` },
    { q: "¿Cómo corrijo un error en el registro?", a: `Haz clic en el movimiento, elige <b>Editar movimiento</b>, cámbialo y elige <b>Guardar cambios</b>. Para quitarlo, usa el bote de basura mientras lo editas.` },
    { q: "¿Mi pareja y yo podemos compartir cuentas?", a: `Sí. Dale a cada persona su propio acceso (Personas), luego comparte una cuenta con su entorno, o hazla miembro del tuyo. Ver <a href="#/help/people">Personas, entornos y compartir</a>.` },
    { q: "¿Puedo usarlo en mi teléfono?", a: `Sí, en el navegador del teléfono, en tu red de casa o por Tailscale. Agregar rápido (el botón +) está hecho para teléfonos. Ver <a href="#/help/quick">Agregar rápido</a>.` },
    { q: "¿Dónde se guardan mis datos?", a: `En la carpeta de datos indicada en Configuración → Esta computadora: en una computadora, tu propia carpeta de datos de aplicaciones; en Docker o Unraid, la carpeta de datos que mapeaste. Los respaldos van a donde los configuraste en Configuración → Respaldos.` },
    { q: "Olvidé la contraseña de cifrado de los respaldos.", a: `Los respaldos cifrados no se pueden abrir sin ella, a propósito. Tu archivo de dinero no se ve afectado: pon una contraseña nueva en Configuración → Respaldos y haz un respaldo nuevo enseguida.` },
    { q: "¿Cómo restauro un respaldo?", a: `Configuración → Respaldos → elige el respaldo → Restaurar. MoneyThistle primero hace una copia de seguridad de lo que tienes.` },
    { q: "¿Restaurar un respaldo también regresa la versión anterior de MoneyThistle?", a: `No: una restauración trae de vuelta tus datos (cuentas, movimientos, recibos, personas), nunca el programa. El MoneyThistle que tienes sigue funcionando y lee los datos anteriores. Un respaldo hecho por un MoneyThistle <i>más nuevo</i> que el tuyo se rechaza hasta que actualices, para que nada se pierda ni se mezcle.` },
    { q: "¿Es seguro abrir MoneyThistle desde internet?", a: `No: mantenlo en tu red de casa o en Tailscale. Ver <a href="#/help/safety">Mantenerlo seguro</a>.` },
    { q: "Olvidé mi contraseña.", a: `Usa <i>¿Olvidaste tu contraseña?</i> en la página de inicio de sesión, pide ayuda a un administrador, o ve <a href="#/help/signin">Inicio de sesión y contraseñas olvidadas</a> para la forma de volver a entrar que funciona sin correo.` },
    { q: "¿Puedo traer mi historial de Microsoft Money o Quicken?", a: `Sí: cada cuenta, categoría y transacción. Ver <a href="#/help/move-in">Mudarse desde otro programa</a>.` },
    { q: "¿Cómo veo el recorrido otra vez?", a: `Elige <b>Hacer el recorrido</b> arriba en esta página de Ayuda.` },
    { q: "¿Cómo quito los datos de ejemplo, o empiezo de cero?", a: `Mientras uses los datos de ejemplo, una barra arriba en
      cada página ofrece <b>Empezar de cero con mi propio dinero</b>. Más adelante, un propietario puede empezar un entorno de
      cero en Configuración → Tus datos (escribiendo su nombre para confirmar): se van las cuentas, movimientos, la agenda, el
      presupuesto y los recibos; las personas, inicios de sesión, la configuración de respaldos y los otros entornos se quedan, y
      se guarda una copia de lo que había en la carpeta de datos de MoneyThistle.` },
    { q: "¿Cómo mantengo al día el valor de una inversión?", a: `MoneyThistle no busca valores. Abre la cuenta y elige
      <b>Actualizar valor</b>, y escribe cuánto vale según su estado de cuenta o su sitio: la diferencia entra como un movimiento de
      <i>Cambio de valor</i>, fuera de los presupuestos y los informes de gastos. Las cuentas de inversión y jubilación lo
      recuerdan cada mes (junto a los estados de las tarjetas); apágalo, o enciéndelo para un bien como una casa, en los detalles de la cuenta.` },
    { q: "¿Puedo ver qué haría un pago extra a mi préstamo?", a: `Sí. Abre la cuenta del préstamo y elige <b>¿Y si…?</b> en su tarjeta Préstamo.
      Prueba un pago extra al capital una vez (con el pago de la fecha que elijas), un extra en cada pago, o pagar dos veces
      al mes o cada dos semanas en lugar de mensualmente. Muestra cuándo quedaría pagado y cuántos intereses costaría, junto a
      cómo está ahora. No se guarda nada; pregunta a tu prestamista antes de cambiar cómo pagas. Para calcular un préstamo que
      aún no tienes, como cuánto auto puede comprar un pago mensual, usa la <b>Calculadora de préstamos</b> debajo de la lista
      de cuentas en la página Cuentas; <b>Crear este préstamo…</b> empieza uno nuevo a partir de ella.` },
    { q: "¿Qué es la taza de café?", a: `MoneyThistle es gratuito. La pequeña taza arriba y la línea al pie de la página llevan a la
      página de Buy Me a Coffee de su autor, para quien quiera aportar; nunca se espera nada, y no se envía nada allí a menos
      que hagas clic. Para ocultarlas solo para ti, desmárcalas en Configuración → Apariencia → Taza de café; un
      administrador también puede ocultarlas para todos.` },
    { q: "¿Dónde cambio la cuenta que paga una tarjeta de crédito?", a: `En cualquiera de los dos lugares: los <b>Detalles de la cuenta</b>
      de la tarjeta (Pagar desde), o su pago en <b>Facturas y depósitos</b> (ábrelo y cambia la cuenta, el monto o la fecha).
      Cada uno sigue al otro. Un pago que quedó atrás al mover una tarjeta o una cuenta entre entornos lo retoma la tarjeta la
      próxima vez que se guardan sus detalles: nunca hay dos.` },
  ],
  terms: [
    { term: "Cuenta", def: "Donde se guarda o se debe dinero: cuenta corriente, ahorros, tarjeta de crédito, préstamo, inversión." },
    { term: "Registro", def: "La lista de movimientos de una cuenta con su saldo acumulado, como una chequera." },
    { term: "Movimiento", def: "Una línea en un registro: dinero que entra o sale en una fecha." },
    { term: "Beneficiario", def: "A quién le pagaste o quién te pagó." },
    { term: "Categoría", def: "Para qué fue el dinero (Supermercado, Renta) o de dónde vino (Sueldos). Las categorías principales pueden tener subcategorías." },
    { term: "Relacionado con impuestos", def: "Una categoría cuyos movimientos van al informe fiscal de fin de año. Se define en Categorías." },
    { term: "Transferencia (mover)", def: "Dinero que pasa entre dos de tus propias cuentas: un movimiento en cada registro, unidos." },
    { term: "Dividido", def: "Un pago hecho de partes en distintas categorías o cuentas, como un pago de préstamo (capital, intereses, depósito en garantía) o un recibo de nómina." },
    { term: "Conciliado (C)", def: "Tu banco ya procesó el movimiento." },
    { term: "Verificado (R)", def: "El movimiento se cuadró contra un estado de cuenta con Conciliar la cuenta." },
    { term: "Elemento programado", def: "Una factura, depósito, transferencia o pago en Facturas y depósitos que se repite." },
    { term: "Automático ⟳", def: "Un elemento programado que pasa solo; con 'registrarlo por mí', MoneyThistle lo registra en su fecha." },
    { term: "Saldo del estado de cuenta", def: "Lo que el estado de cuenta de una tarjeta dice que debes a la fecha de corte." },
    { term: "Día de corte / de pago", def: "El día en que cierra el estado de cuenta de una tarjeta, y el día en que vence su pago. 31 significa el último día del mes." },
    { term: "Sueldo bruto", def: "Sueldo antes de impuestos y deducciones." },
    { term: "Sueldo neto", def: "Lo que llega a tu cuenta después de impuestos y deducciones." },
    { term: "Deducción antes de impuestos", def: "Se toma del sueldo antes del impuesto sobre la renta, como un 401(k), una HSA por nómina o un seguro médico. Reduce el salario gravable (W-2 casilla 1)." },
    { term: "HSA", def: "Cuenta de ahorro para la salud (EE. UU.): dinero para gastos médicos con ventajas fiscales, hasta un límite anual sumando todas tus HSA." },
    { term: "Entorno", def: "Un grupo separado de cuentas (Personal, Negocio…) que solo ven sus miembros." },
    { term: "Cuenta compartida", def: "Una cuenta que se muestra también en otro entorno: un registro y un saldo vistos en ambos." },
    { term: "Patrimonio neto", def: "Todo lo que tienes menos todo lo que debes." },
    { term: "Pronóstico", def: "Saldos proyectados desde hoy usando tu calendario (Informes → Lo que viene)." },
    { term: "WebDAV", def: "Una forma estándar de guardar archivos en un servidor; Nextcloud la usa. Sirve para los respaldos." },
    { term: "Tailscale", def: "Una red privada entre tus propios dispositivos, para que un teléfono fuera de casa alcance MoneyThistle sin exponerlo a internet." },
  ],
});
