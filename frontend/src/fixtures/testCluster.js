/**
 * Демо-кластер для проверки UI после нормализации:
 * шаблон, members, aliases, аккумулятивное слияние (, и ;), меню строк.
 */
export function buildTestClusters() {
  return [
    {
      name: "Тест: фильтры (демо)",
      attributes: ["бренд", "артикул", "цвет", "OEM"],
      enriched_name_template: "{бренд} фильтр {артикул}",
      attribute_merge: {
        бренд: "priority",
        артикул: "priority",
        цвет: "accumulative",
        OEM: "accumulative",
      },
      attribute_merge_separators: {
        OEM: "; ",
      },
      rows: [
        {
          enriched_name: "Donaldson фильтр P551551",
          item: "Donaldson фильтр P551551",
          aliases: [
            "Фильтр масляный Donaldson P551551",
            "Oil filter Donaldson P551551",
          ],
          source: "memory",
          values: {
            бренд: "Donaldson",
            артикул: "P551551",
            цвет: "красный, синий",
            OEM: "DN-01; DN-02",
          },
          members: [
            {
              item: "Фильтр масляный Donaldson P551551",
              source: "memory",
              values: {
                бренд: "Donaldson",
                артикул: "P551551",
                цвет: "красный, синий",
                OEM: "DN-01",
              },
            },
            {
              item: "Oil filter Donaldson P551551",
              source: "ai",
              values: {
                бренд: "Donaldson",
                артикул: "P551551",
                цвет: "",
                OEM: "DN-02",
              },
            },
          ],
        },
        {
          enriched_name: "Donaldson фильтр P551551",
          item: "Donaldson фильтр P551551 (аналог)",
          aliases: ["Фильтр Donaldson аналог P551551"],
          source: "ai",
          values: {
            бренд: "Donaldson",
            артикул: "P551551",
            цвет: "зеленый",
            OEM: "DN-03",
          },
          members: [
            {
              item: "Фильтр Donaldson аналог P551551",
              source: "ai",
              values: {
                бренд: "Donaldson",
                артикул: "P551551",
                цвет: "зеленый",
                OEM: "DN-03",
              },
            },
          ],
        },
        {
          enriched_name: "IEK кабель ВВГ 3x1.5",
          item: "IEK кабель ВВГ 3x1.5",
          aliases: ["Кабель IEK ВВГнг 3х1.5"],
          source: "ai",
          values: {
            бренд: "IEK",
            артикул: "ВВГ 3x1.5",
            цвет: "белый; серый",
            OEM: "IEK-100",
          },
          members: [
            {
              item: "Кабель IEK ВВГнг 3х1.5",
              source: "ai",
              values: {
                бренд: "IEK",
                артикул: "ВВГ 3x1.5",
                цвет: "белый; серый",
                OEM: "IEK-100",
              },
            },
          ],
        },
      ],
    },
  ];
}
