# GraphQL queries for Twenty CRM metadata operations

# Query to get all object metadata
GET_OBJECTS_QUERY = """
query GetObjectsMetadata {
  objects {
    edges {
      node {
        id
        nameSingular
        namePlural
        labelSingular
        labelPlural
        description
        icon
        isActive
        isSystem
        fields {
          edges {
            node {
              id
              name
              label
              type
              description
              icon
              isActive
            }
          }
        }
      }
    }
  }
}
"""

# Mutation to create a new object
CREATE_OBJECT_MUTATION = """
mutation CreateObjectMetadata($input: CreateObjectInput!) {
  createObject(input: $input) {
    id
    nameSingular
    namePlural
    labelSingular
    labelPlural
    description
    icon
  }
}
"""

# Mutation to create a field on an object
CREATE_FIELD_MUTATION = """
mutation CreateFieldMetadata($input: CreateFieldInput!) {
  createField(input: $input) {
    id
    name
    label
    type
    description
    icon
  }
}
"""

# Mutation to create a relation between objects
CREATE_RELATION_MUTATION = """
mutation CreateRelationMetadata($input: CreateRelationInput!) {
  createRelation(input: $input) {
    id
    relationType
    fromObjectMetadataId
    toObjectMetadataId
  }
}
"""

# Query to find an object by name
GET_OBJECT_BY_NAME_QUERY = """
query GetObjectByName($nameSingular: String!) {
  findObjectMetadataByName(nameSingular: $nameSingular) {
    id
    nameSingular
    namePlural
    labelSingular
    labelPlural
    description
    icon
    isActive
    isSystem
    fields {
      edges {
        node {
          id
          name
          label
          type
          description
          icon
          isActive
        }
      }
    }
  }
}
"""

# Website Analysis object metadata definition
WEBSITE_ANALYSIS_OBJECT = {
    "nameSingular": "websiteAnalysis",
    "namePlural": "websiteAnalyses",
    "labelSingular": "Website Analysis",
    "labelPlural": "Website Analyses",
    "description": "Website quality analysis for prospects",
    "icon": "IconWorld",
}

# Website Analysis field definitions
WEBSITE_ANALYSIS_FIELDS = [
    {
        "name": "companyId",
        "label": "Company",
        "type": "RELATION",
        "description": "Related company",
        "icon": "IconBuilding",
    },
    {
        "name": "websiteUrl",
        "label": "Website URL",
        "type": "TEXT",
        "description": "Company website URL",
        "icon": "IconLink",
    },
    {
        "name": "hasWebsite",
        "label": "Has Website",
        "type": "BOOLEAN",
        "description": "Whether the company has a website",
        "icon": "IconCheck",
    },
    {
        "name": "designScore",
        "label": "Design Score",
        "type": "NUMBER",
        "description": "Website design quality score (0-100)",
        "icon": "IconPalette",
    },
    {
        "name": "performanceScore",
        "label": "Performance Score",
        "type": "NUMBER",
        "description": "Website performance score (0-100)",
        "icon": "IconSpeedometer",
    },
    {
        "name": "mobileCompatibility",
        "label": "Mobile Compatibility",
        "type": "NUMBER",
        "description": "Mobile compatibility score (0-100)",
        "icon": "IconDeviceMobile",
    },
    {
        "name": "seoScore",
        "label": "SEO Score",
        "type": "NUMBER",
        "description": "Search engine optimization score (0-100)",
        "icon": "IconSearch",
    },
    {
        "name": "techStack",
        "label": "Technology Stack",
        "type": "ARRAY",
        "description": "Technologies used on the website",
        "icon": "IconCode",
    },
    {
        "name": "improvementOpportunities",
        "label": "Improvement Opportunities",
        "type": "TEXT",
        "description": "Key improvement opportunities",
        "icon": "IconBulb",
    },
    {
        "name": "analysisDate",
        "label": "Analysis Date",
        "type": "DATE_TIME",
        "description": "When the analysis was performed",
        "icon": "IconCalendar",
    },
]

# Fields to add to Company object
COMPANY_EXTENSION_FIELDS = [
    {
        "name": "webDevPriority",
        "label": "Web Dev Priority",
        "type": "SELECT",
        "description": "Lead priority for web development",
        "icon": "IconFlag",
        "options": ["High", "Medium", "Low", "Not Qualified"],
        "defaultValue": "Medium",
    },
    {
        "name": "websiteStatus",
        "label": "Website Status",
        "type": "SELECT",
        "description": "Current website status",
        "icon": "IconWorld",
        "options": [
            "No Website",
            "Basic Website",
            "Modern Website",
            "E-commerce",
            "Unknown",
        ],
        "defaultValue": "Unknown",
    },
    {
        "name": "lastProspected",
        "label": "Last Prospected",
        "type": "DATE_TIME",
        "description": "When the company was last researched",
        "icon": "IconClockCheck",
    },
    {
        "name": "proposedSolution",
        "label": "Proposed Solution",
        "type": "TEXT",
        "description": "Proposed web solution based on analysis",
        "icon": "IconBulb",
    },
]
