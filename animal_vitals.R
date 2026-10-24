# ============================================================
#  animal_vitals.R
#  PawWatch — healthy resting vital ranges for many animals.
#  Load, summarise, and classify a live reading as normal / abnormal.
#
#  Data source: Merck Veterinary Manual, VCA, Cornell Feline Health.
#  Values are RESTING ranges for a healthy animal of that type/stage.
#
#  Run:  Rscript animal_vitals.R
#  Needs base R only. (dplyr/ggplot2 used only if installed.)
# ============================================================

# ---- 1. The dataset, built right into the script so it exports cleanly ----

animal_vitals <- data.frame(
  animal_group = c("Pet","Pet","Pet","Pet","Pet","Pet","Pet","Pet","Pet","Pet",
                   "Pet","Pet","Pet","Pet","Pet","Pet","Pet","Pet","Pet","Pet",
                   "Farm","Farm","Farm","Farm","Farm","Farm","Farm","Farm","Farm",
                   "Farm","Farm","Farm","Large","Large","Large","Large","Large"),
  species = c("Dog","Dog","Dog","Dog","Dog","Dog","Dog","Dog","Dog","Dog",
              "Dog","Dog","Cat","Cat","Cat","Cat","Cat","Rabbit","Rabbit","Ferret",
              "Cow","Cow","Cow","Horse","Horse","Horse","Sheep","Sheep","Goat",
              "Goat","Pig","Pig","Cattle","Elephant","Elephant","Llama","Deer"),
  breed_or_type = c("Chihuahua","Yorkshire Terrier","Pomeranian","Beagle","French Bulldog",
                    "Border Collie","Labrador Retriever","German Shepherd","Golden Retriever",
                    "Great Dane","Saint Bernard","Mixed Puppy","Domestic Shorthair","Maine Coon",
                    "Siamese","Persian","Kitten","Mini Rex","Flemish Giant","Standard Ferret",
                    "Holstein Dairy","Angus Beef","Calf","Thoroughbred","Pony","Foal",
                    "Adult Sheep","Lamb","Adult Goat","Kid","Adult Pig","Piglet",
                    "Adult Bull","African Elephant","Asian Elephant","Llama/Alpaca","Farmed Deer"),
  age_stage = c("adult","adult","adult","adult","adult","adult","adult","adult","adult",
                "adult","adult","puppy","adult","adult","adult","adult","kitten","adult",
                "adult","adult","adult","adult","calf","adult","adult","foal","adult","lamb",
                "adult","kid","adult","piglet","adult","adult","adult","adult","adult"),
  size_band = c("toy","toy","toy","small","small","medium","large","large","large","giant",
                "giant","small","small","large","small","small","toy","toy","small","toy",
                "giant","giant","large","giant","large","large","medium","small","medium",
                "small","large","small","giant","giant","giant","large","large"),
  hr_min = c(100,100,100,90,90,80,70,70,70,60,60,120,140,120,150,140,160,180,140,180,
             48,40,100,28,32,70,60,100,70,100,60,100,36,25,28,60,40),
  hr_max = c(140,140,140,130,130,120,110,110,110,100,100,160,200,180,210,200,220,250,200,250,
             84,70,140,44,48,100,90,130,90,130,90,130,60,35,40,90,70),
  resp_min = c(18,18,18,16,16,14,14,14,14,12,12,20,20,18,22,20,25,32,30,33,
               26,20,30,8,10,20,16,20,15,20,12,20,18,4,4,10,12),
  resp_max = c(34,34,34,30,30,28,26,26,26,22,22,40,30,28,34,30,40,60,55,36,
               50,40,60,16,18,40,34,40,30,40,24,40,36,12,12,30,30),
  temp_min_c = c(38.3,38.3,38.3,38.3,38.3,38.3,38.3,38.3,38.3,38.3,38.3,38.3,38.1,38.1,38.1,
                 38.1,38.1,38.5,38.5,37.8,38.0,38.0,38.0,37.2,37.2,37.2,38.5,38.5,38.5,38.5,
                 38.7,38.7,38.0,35.9,35.9,37.5,38.3),
  temp_max_c = c(39.2,39.2,39.2,39.2,39.2,39.2,39.2,39.2,39.2,39.2,39.2,39.5,39.2,39.2,39.2,
                 39.2,39.5,40.0,40.0,40.0,39.3,39.3,39.3,38.3,38.3,38.3,40.0,40.0,39.7,39.7,
                 39.8,39.8,39.3,37.2,37.2,38.9,39.4),
  activity_min = c(20,20,20,30,25,45,40,40,40,25,20,40,20,25,30,15,40,15,10,30,
                   20,20,30,20,25,30,20,30,25,35,20,30,20,15,15,20,25),
  activity_max = c(60,60,60,80,70,95,90,90,90,70,65,95,70,75,85,60,95,55,45,90,
                   70,70,85,80,80,90,70,85,80,90,70,85,70,60,60,75,85),
  stringsAsFactors = FALSE
)

# ---- 2. Quick summary table (mid-points per animal) ----

animal_vitals$hr_mid       <- (animal_vitals$hr_min + animal_vitals$hr_max) / 2
animal_vitals$resp_mid     <- (animal_vitals$resp_min + animal_vitals$resp_max) / 2
animal_vitals$temp_mid_c   <- (animal_vitals$temp_min_c + animal_vitals$temp_max_c) / 2

summarise_by_species <- function(df = animal_vitals) {
  agg <- aggregate(cbind(hr_mid, resp_mid, temp_mid_c) ~ species,
                   data = df, FUN = function(x) round(mean(x), 1))
  agg[order(-agg$hr_mid), ]
}

# ---- 3. Classify a live reading as NORMAL or ABNORMAL ----
#   type_name : the breed_or_type string, e.g. "Labrador Retriever"
#   signal    : "hr", "resp", or "temp"
#   value     : the measured number

classify_reading <- function(type_name, signal, value, df = animal_vitals) {
  row <- df[df$breed_or_type == type_name, ]
  if (nrow(row) == 0) stop(paste("Unknown animal type:", type_name))
  lo <- switch(signal, hr = row$hr_min, resp = row$resp_min, temp = row$temp_min_c)
  hi <- switch(signal, hr = row$hr_max, resp = row$resp_max, temp = row$temp_max_c)
  status <- if (value < lo) "LOW"
            else if (value > hi) "HIGH"
            else "NORMAL"
  data.frame(type = type_name, signal = signal, value = value,
             normal_low = lo, normal_high = hi, status = status)
}

# ---- 4. Export back out for the app (same CSV shape it reads) ----

export_for_app <- function(path = "animal_vitals_export.csv", df = animal_vitals) {
  cols <- c("animal_group","species","breed_or_type","age_stage","size_band",
            "hr_min","hr_max","resp_min","resp_max","temp_min_c","temp_max_c",
            "activity_min","activity_max")
  write.csv(df[, cols], path, row.names = FALSE)
  message("Exported ", nrow(df), " animal rows to ", path)
}

# ---- 5. Run when called directly ----

if (sys.nframe() == 0) {
  cat("=== Average vitals by species (fastest heart first) ===\n")
  print(summarise_by_species())

  cat("\n=== Example checks ===\n")
  print(classify_reading("Labrador Retriever", "hr", 150))   # HIGH -> alarm
  print(classify_reading("African Elephant",   "hr", 30))    # NORMAL
  print(classify_reading("Domestic Shorthair", "temp", 40.5))# HIGH -> fever

  export_for_app()
}
