from examples.a2e_buoy_ingest import (
    BuoyIngestPipeline,
    STORAGE_CONFIG,
    HUMBOLDT_CONFIG,
    HUMBOLDT_FILE,
    MORRO_CONFIG,
    MORRO_FILE,
)


def run_pipelines():

    # Run the ingest for Humboldt
    humboldt_pipeline = BuoyIngestPipeline(HUMBOLDT_CONFIG, STORAGE_CONFIG)
    humboldt_pipeline.run(HUMBOLDT_FILE)

    # Run the ingest for Morro Bay
    morro_pipeline = BuoyIngestPipeline(MORRO_CONFIG, STORAGE_CONFIG)
    morro_pipeline.run(MORRO_FILE)


if __name__ == "__main__":
    run_pipelines()