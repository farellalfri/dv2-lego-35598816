var vg_1 = "js/map1_choropleth.vg.json";
vegaEmbed("#map1", vg_1, {"actions": false}).then(function(result) {
  // Access the Vega view instance (https://vega.github.io/vega/docs/api/view/) as result.view
}).catch(console.error);

var vg_2 = "js/map3_world_imports.vg.json";
vegaEmbed("#map3", vg_2, {"actions": false}).then(function(result) {
  // Access the Vega view instance as result.view
}).catch(console.error);

var vg_3 = "js/chart8_ages_12plus.vg.json";
vegaEmbed("#chart8", vg_3, {"actions": false}).then(function(result) {
  // Access the Vega view instance as result.view
}).catch(console.error);

var vg_4 = "js/chart2_histograms_by_decade.vg.json";
vegaEmbed("#chart2", vg_4, {"actions": false}).then(function(result) {
  // Access the Vega view instance as result.view
}).catch(console.error);